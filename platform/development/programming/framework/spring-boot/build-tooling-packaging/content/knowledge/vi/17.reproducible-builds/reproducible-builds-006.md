# Cấu hình thứ tự tệp và timestamp tái lập cho archive Gradle

## 1. Mục tiêu và động cơ

Khi một nhóm build cùng một commit Spring Boot trên laptop và CI, kết quả lý tưởng là **cùng một artifact có cùng bytes và cùng SHA-256**. Thực tế, hai file JAR hoặc WAR đôi khi chạy giống hệt nhau nhưng hash khác vì file entries trong archive có thứ tự khác, timestamp của từng entry thay đổi, quyền truy cập bị lấy từ filesystem, hoặc task sinh thêm metadata theo giờ.

**Reproducible archive** là một phần quan trọng của bản dựng tái lập (*reproducible build*): nếu input, toolchain và môi trường có ảnh hưởng được giữ ổn định thì artifact ZIP/JAR/WAR/TAR cũng phải ổn định đến từng byte. Việc này giúp đối chiếu provenance, xác minh artifact phát hành, phát hiện thay đổi ngoài ý muốn, giảm cache miss ở các tác vụ phụ thuộc và hỗ trợ supply-chain security.

Sau bài học, bạn có thể:

1. Hiểu vì sao **thứ tự tệp (entry order)** và **timestamp của các entry** ảnh hưởng byte của archive dù nội dung nguồn không đổi.
2. Dùng `reproducibleFileOrder = true` và `preserveFileTimestamps = false` với các task thuộc `AbstractArchiveTask` của Gradle.
3. Phân biệt **default trên Gradle 9.0+** với cách cấu hình tường minh khi còn hỗ trợ Gradle 8.x hoặc bản cũ hơn.
4. Áp dụng cho `Jar`, `Zip`, `Tar`, `War` và Spring Boot `bootJar`/`bootWar`; biết điểm nào cần kiểm tra riêng theo plugin version.
5. Dựng một project Java 17 + Spring Boot có thể chạy, đóng gói ZIP và Boot JAR, rồi dùng **hai lượt build sạch không lấy output từ build cache** để so sánh SHA-256.
6. Chẩn đoán hash khác vì manifest, generated resources, compiler/toolchain, dependency version, file permissions, thư viện lồng trong JAR hoặc metadata khác.
7. Thiết kế một bước xác minh build reproducibility cho CI và biết giới hạn của chứng cứ “hash bằng nhau”.

**Giả định thực hành:** Java 17, Spring Boot Gradle Plugin 3.3.5 và Gradle Wrapper **8.x tương thích** để làm ví dụ. Những version này chỉ để minh họa cấu hình, không phải khuyến nghị bản mới nhất. Gradle 9.0+ và 9.7+ được thảo luận riêng vì defaults/API đã thay đổi; chỉ dùng các API mới khi Spring Boot/plugin và Gradle của dự án thực sự tương thích.

## 2. Hiểu cấu trúc archive: bytes quan trọng hơn file name

JAR và WAR là các định dạng ZIP có quy ước nội dung; mỗi ZIP entry có **tên, dữ liệu, thông tin nén và metadata**, trong đó có timestamp. TAR cũng lưu metadata riêng của member. Vì thế, archive có thể khác bytes dù giải nén ra những file có cùng nội dung.

Ví dụ hai ZIP đều chứa hai file:

~~~text
Archive A
  alpha.txt  timestamp: lượt build A
  beta.txt   timestamp: lượt build A

Archive B
  beta.txt   timestamp: lượt build B
  alpha.txt  timestamp: lượt build B
~~~

Kể cả khi nội dung của `alpha.txt` và `beta.txt` giống nhau, **entry order và timestamp metadata** khác có thể khiến SHA-256 của ZIP khác. Không được dùng quy tắc “đã giải nén và diff folder không thấy khác” để kết luận archive giống byte-for-byte.

### Hai lớp timestamp khác nhau

| Thời gian | Nằm ở đâu? | Có được điều khiển bằng `preserveFileTimestamps`? |
| --- | --- | --- |
| **Archive entry timestamp** | Metadata của từng file bên trong ZIP/JAR/WAR/TAR | Có: đặt `false` để Gradle dùng timestamp ổn định theo loại archive |
| **Filesystem mtime của chính file .jar/.zip** | Metadata của file archive trên ổ đĩa sau build/copy | Không trực tiếp: mỗi lần viết file có thể cập nhật mtime của *file ngoài*, ngay cả khi bytes bên trong trùng |
| **Thời gian trong generated file/manifest** | Nội dung text như `Built-At: 2026-...` hoặc `build.time=...` | Không: phải sửa chính generator hoặc không đưa dữ liệu biến động vào artifact |
| **Thời gian từ code/runtime logs** | Log khi chạy chương trình | Không liên quan đến SHA-256 của archive nếu log không được ghi vào archive |

**Khi kiểm tra reproducibility, so sánh SHA-256 của file archive**. Đừng lấy thời gian hiển thị trong File Explorer, Finder hay lệnh `ls -l` của archive ngoài làm bằng chứng thất bại.

### Thứ tự file và thứ tự đường dẫn

`reproducibleFileOrder` bảo đảm Gradle duyệt các file trong **các thư mục đầu vào** theo thứ tự tái lập, thay vì phụ thuộc thứ tự directory iteration của filesystem/OS. Nó **không phải công tắc sắp xếp ngẫu nhiên tất cả các entry bất kể nguồn, CopySpec, dependency ordering hoặc nested archive**.

Để archive thực sự ổn định, mọi input của các `from(...)`, manifest properties, dependency JARs và output của task nguồn cũng phải có hành vi xác định. Nếu một script tạo file từ `HashMap` iteration rồi nhúng thứ tự vào text, đổi hai flag archive **không sửa được nội dung text ấy**.

## 3. Hai thuộc tính Gradle cốt lõi

Phần lớn archive tasks kế thừa `org.gradle.api.tasks.bundling.AbstractArchiveTask`. Chúng có hai Boolean properties:

| Property | Giá trị nên dùng | Tác dụng |
| --- | --- | --- |
| `reproducibleFileOrder` | `true` | Duyệt file từ directory inputs theo thứ tự ổn định giữa các filesystem/OS |
| `preserveFileTimestamps` | `false` | Không giữ timestamps gốc của file nguồn trong các archive entries; dùng giá trị ổn định do Gradle quy định |
| `reproducibleFileTimestamp` | Tùy chọn trên Gradle 9.7+ | Cấp một **timestamp xác định** (mili-giây epoch) cho mọi entry thay vì giá trị cố định mặc định; cần `preserveFileTimestamps=false` |

### Phân biệt Gradle 8.x và 9.x

- **Gradle trước 9.0:** các task archive hỗ trợ hai Boolean properties, nhưng **không mặc định bật đầy đủ chế độ reproducible như Gradle 9**. Nếu muốn bảo đảm kết quả, cấu hình `false/true` tường minh trong build.
- **Gradle 9.0 trở lên:** theo tài liệu Gradle, `AbstractArchiveTask` mặc định `preserveFileTimestamps=false` và `reproducibleFileOrder=true`; đồng thời các file/dir entries có permissions mặc định ổn định (`0644` cho file, `0755` cho directory).
- **Gradle 9.7 trở lên:** API incubating `reproducibleFileTimestamp` cho phép chọn timestamp cố định riêng. **Không gọi thuộc tính này trong project chạy Gradle 8.x**, vì API không tồn tại ở đó.

Do đó **đừng sao chép lời khuyên “mặc định luôn là false/true” cho mọi phiên bản**. Kiểm tra `./gradlew --version` hoặc `.\gradlew.bat --version` trước khi quyết định có cần cấu hình hay không.

### Khi nào không nên preserve timestamps?

Khi mục tiêu là artifact byte-for-byte reproducible, thường **không** giữ timestamps từ filesystem. Ngay cả checkout cùng commit, các file trên máy A và máy B có thể có mtime khác; `preserveFileTimestamps=true` sẽ mang biến động ấy vào archive.

### Nếu file permissions quan trọng?

Gradle 9+ cũng bình thường hóa permissions theo defaults. Với các bản Gradle cũ, bản dựng trên máy Unix có `umask` và executable bits khác nhau có thể ảnh hưởng archive. Các API như `filePermissions` và `dirPermissions` có thể giúp cấu hình cụ thể **nếu phiên bản Gradle hỗ trợ**; không tùy tiện áp đặt `0644` cho shell script phải executable. Chỉ đặt permissions có chủ đích và kiểm tra khả năng chạy của script sau khi giải nén.

## 4. Cấu hình Groovy DSL cho tất cả archive tasks

Trong `build.gradle`, khi project đã có plugins, có thể thêm:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Đây là trích đoạn**, không phải toàn bộ project. Nếu file đã có `import` và `plugins`, đặt import ở đầu file và block `tasks.withType...` ở vị trí build script hợp lệ; không tạo hai cấu hình cùng điều khiển flag mâu thuẫn.

Giải thích:

1. `tasks.withType(AbstractArchiveTask)` chọn các task có kiểu con của `AbstractArchiveTask` trong **project hiện tại**, gồm `Jar`, `Zip`, `Tar`, `War` và các task phù hợp do plugin áp dụng.
2. `configureEach` cấu hình theo cơ chế lazy configuration, áp dụng cả với task được plugin đăng ký sau đó mà không phải eager-realize mọi task.
3. `preserveFileTimestamps=false` và `reproducibleFileOrder=true` điều khiển metadata của archive entries và thứ tự duyệt input files.
4. Cấu hình **không thêm task mới** và **không chọn dependency version**; nó chỉ thay hành vi archive tasks đã được project đăng ký.
5. Với multi-project build, block ở root project không tự đảm bảo các **subproject** có cùng cấu hình. Nên đặt trong convention plugin dùng chung hoặc cấu hình trong từng module theo kiến trúc build của tổ chức.

### Chỉ áp dụng cho một task

Nếu nhóm muốn thay đổi đúng một archive thay vì mọi archive:

~~~groovy
tasks.named('jar', Jar) {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Hoặc với task Spring Boot:

~~~groovy
tasks.named('bootJar') {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

`bootJar` của Spring Boot Gradle Plugin là subtype của `Jar` qua `BootJar`, nên có các archive properties kế thừa. Với một application module chỉ dùng `bootJar`, scope hẹp có thể dễ review hơn cấu hình tất cả task.

**Không sửa `jar` rồi giả định `bootJar` cũng được sửa.** Chúng là **hai tasks khác nhau**, dù cùng có nguồn file tương tự. Nếu CI phát hành Boot executable JAR, hãy kiểm tra cấu hình của chính `bootJar`.

## 5. Kotlin DSL tương đương

Trong `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Lưu ý sự khác biệt tên property trong Kotlin DSL:

- Groovy: `preserveFileTimestamps`, `reproducibleFileOrder`.
- Kotlin: `isPreserveFileTimestamps`, `isReproducibleFileOrder`.

Đây là các property Boolean trên task, **không phải Gradle project properties**. Viết `org.gradle.reproducibleFileOrder=true` vào `gradle.properties` không phải cách chính thức để bật hai thuộc tính ấy cho toàn bộ archive tasks.

Với task cụ thể, Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Đoạn `import` ở đầu file build. Chọn bản Groovy **hoặc** Kotlin theo dự án; không trộn hai cú pháp vào một file.

## 6. Project mẫu: Spring Boot executable JAR và ZIP tài liệu

Ta xây một project Gradle Groovy DSL có hai artifact để so sánh:

- `build/distributions/source-data.zip` được tạo từ các file text, minh họa trực tiếp thứ tự file và timestamp entries.
- `build/libs/archive-demo-0.0.1-SNAPSHOT.jar` là executable Spring Boot JAR; xác minh rằng lựa chọn cấu hình cũng áp dụng cho `BootJar` và không phá khả năng chạy `java -jar`.

### 6.1. Cấu trúc thư mục

~~~text
archive-demo/
├── settings.gradle
├── build.gradle
├── gradlew, gradlew.bat, gradle/wrapper/
└── src/
    └── main/
        ├── archive-data/
        │   ├── alpha.txt
        │   └── beta.txt
        └── java/com/example/archive/
            └── ArchiveDemoApplication.java
~~~

Ví dụ giả định bạn đã tạo project Gradle có Wrapper hợp lệ; **không tự gõ file `gradlew` và bỏ qua wrapper jar**. Nếu đang sửa một Spring Boot project thật, tích hợp chỉ phần cấu hình archive thay vì ghi đè build file hiện hữu.

### 6.2. File settings.gradle

~~~groovy
rootProject.name = 'archive-demo'
~~~

### 6.3. File dữ liệu thứ nhất: src/main/archive-data/alpha.txt

~~~text
alpha
~~~

### 6.4. File dữ liệu thứ hai: src/main/archive-data/beta.txt

~~~text
beta
~~~

Các file này là input của `packageDocuments`, **không nằm trong `src/main/resources`** để tránh ảnh hưởng bất ngờ tới Boot JAR. Thứ tự tệp trên filesystem có thể khác giữa máy, nhưng archive task sẽ duyệt directory inputs theo thứ tự reproducible.

### 6.5. File build.gradle hoàn chỉnh

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.bundling.Zip

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.archive.ArchiveDemoApplication'
}

// Tương thích với các Gradle 8.x mà dự án vẫn hỗ trợ.
// Gradle 9.0+ mặc định đã bật hai chế độ này.
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}

tasks.register('packageDocuments', Zip) {
    from('src/main/archive-data')
    archiveFileName = 'source-data.zip'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

**Đây là build script đầy đủ cho ví dụ Groovy DSL.**

- `java.toolchain` chọn Java 17 cho các tác vụ Java; giữ compiler ổn định giữa local/CI khi có JDK phù hợp.
- `spring-boot-starter` tạo ứng dụng Boot tối thiểu không cần web server để chạy kiểm tra JAR.
- `springBoot.mainClass` chỉ rõ application entry point, tránh auto-detection khác nhau nếu sau này thêm nhiều lớp main.
- `tasks.withType(AbstractArchiveTask).configureEach` áp dụng cả cho `packageDocuments` và `bootJar` do Spring Boot plugin đăng ký.
- `packageDocuments` là task kiểu `Zip`, lấy hai file text từ một thư mục cố định và đặt tên output `source-data.zip`.
- `destinationDirectory` đặt ZIP bên dưới `build/distributions`; `clean` xóa các outputs này nhưng **không xóa nguồn dữ liệu**.
- Tệp `BOOT-INF/lib` của Boot JAR được đóng gói bởi Spring Boot plugin, không được lấy từ thư mục `src/main/archive-data`.

**Ghi chú build tool:** version Spring Boot plugin trong ví dụ dùng để minh họa. Nếu project hiện tại đã dùng plugin Spring Boot version khác, không cần hạ/nâng version chỉ để đặt hai archive properties. Không thay đổi dependency management, repositories hoặc Gradle Wrapper trong một PR chỉ nhằm bật reproducibility.

### 6.6. File src/main/java/com/example/archive/ArchiveDemoApplication.java

~~~java
package com.example.archive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ArchiveDemoApplication {

    public static void main(String[] args) {
        System.out.println("ARCHIVE_DEMO_OK");
        SpringApplication.run(ArchiveDemoApplication.class, args);
    }
}
~~~

Mã Java 17+ này đủ để build thành Spring Boot executable JAR với dependency Starter đã khai báo. Vì không có web starter, chương trình thường khởi động rồi thoát sau khi tạo ApplicationContext; không cần kết nối database hoặc mở HTTP port.

Dòng do mã chương trình in ra là:

~~~text
ARCHIVE_DEMO_OK
~~~

Sau đó có thể xuất hiện Spring Boot banner/log với timestamp và PID. **Log lúc chạy có timestamp không làm JAR thay đổi**, vì log không nằm bên trong archive. Đừng nhầm hai loại timestamp.

## 7. Thực thi bước đầu và đọc archive

### Linux/macOS

~~~bash
./gradlew --version
./gradlew --no-build-cache clean packageDocuments bootJar
ls -lh build/distributions/source-data.zip
ls -lh build/libs/archive-demo-0.0.1-SNAPSHOT.jar
jar tf build/distributions/source-data.zip
jar tf build/libs/archive-demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/archive-demo-0.0.1-SNAPSHOT.jar
~~~

### Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --no-build-cache clean packageDocuments bootJar
Get-Item .\build\distributions\source-data.zip
Get-Item .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar
jar tf .\build\distributions\source-data.zip
jar tf .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar
java -jar .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar
~~~

`jar tf` là công cụ từ JDK dùng để liệt kê ZIP/JAR entries; để kiểm tra tính reproducible, bạn còn cần **so hash giữa hai lượt build riêng biệt**, không chỉ xem danh sách tệp một lần.

### Các dấu hiệu cần thấy

- File `source-data.zip` có hai entry `alpha.txt` và `beta.txt`, không thêm file hệ thống hay thư mục ngoài dự kiến.
- Boot JAR có entry như `BOOT-INF/classes/com/example/archive/ArchiveDemoApplication.class`, các nested dependencies và launcher phù hợp với Spring Boot plugin version.
- `java -jar` in `ARCHIVE_DEMO_OK` và không gặp `ClassNotFoundException` liên quan launcher/nested libraries.
- Không có `build.timestamp`, `Built-At` hay dữ liệu clock được bạn tự thêm vào generated resources/manifest.

**Không coi filename, file size hay `BUILD SUCCESSFUL` là chứng cứ byte-for-byte**. Hai JAR cùng tên/cùng kích thước vẫn có thể có SHA-256 khác.

## 8. Thử hai lượt clean build và so sánh SHA-256 — Linux/macOS

Làm trên cùng source checkout và cùng Wrapper/JDK, trước khi sửa bất kỳ file nguồn nào. Đặt bản lưu artifact **ngoài thư mục `build`** vì lệnh `clean` sẽ xóa output của lần trước.

### Bước 1: build lần đầu và lưu artifact

~~~bash
./gradlew --no-build-cache clean packageDocuments bootJar

mkdir -p .repro-check
cp build/distributions/source-data.zip .repro-check/source-data-1.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/application-1.jar

sha256sum .repro-check/source-data-1.zip
sha256sum .repro-check/application-1.jar
~~~

### Bước 2: build lại từ output sạch

~~~bash
./gradlew --no-build-cache clean packageDocuments bootJar

cp build/distributions/source-data.zip .repro-check/source-data-2.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/application-2.jar

sha256sum .repro-check/source-data-2.zip
sha256sum .repro-check/application-2.jar
~~~

### Bước 3: so sánh bytes

~~~bash
cmp -s .repro-check/source-data-1.zip .repro-check/source-data-2.zip \
  && echo "ZIP_IDENTICAL"

cmp -s .repro-check/application-1.jar .repro-check/application-2.jar \
  && echo "JAR_IDENTICAL"
~~~

Nếu hai file ZIP giống hoàn toàn, dòng sau xuất hiện:

~~~text
ZIP_IDENTICAL
~~~

Nếu hai file Boot JAR giống hoàn toàn, dòng sau xuất hiện:

~~~text
JAR_IDENTICAL
~~~

**Hai dòng này là kết quả có điều kiện**, không phải cam kết chúng luôn xuất hiện trong bất cứ dự án nào. Nếu `cmp` phát hiện khác, không in marker tương ứng; dùng `sha256sum` và mục troubleshooting để điều tra. Trong script CI muốn thất bại rõ ràng khi bytes khác, dùng `cmp` riêng với exit code hoặc `set -e` phù hợp, thay vì cho phép điều kiện `&&` bị bỏ qua mà job vẫn pass.

**Vì sao `--no-build-cache`?** Để kiểm tra rằng task **tự tạo lại output cùng bytes**, không phải chỉ khôi phục cùng archive đã được lưu từ một lượt trước. `clean` xóa outputs; build cache khác vẫn có thể restore tasks nếu không tắt. Nếu có plugin custom tạo output ngoài thư mục `build`, còn phải kiểm soát/loại output đó trong phép thử.

## 9. Tương đương trên Windows PowerShell

Trên Windows, nếu có `gradlew.bat` và JDK, có thể dùng `Get-FileHash` (không cần cài sha256sum).

### Bước 1: chạy build và lưu hai archive

~~~powershell
.\gradlew.bat --no-build-cache clean packageDocuments bootJar

New-Item -ItemType Directory -Force .\.repro-check | Out-Null
Copy-Item .\build\distributions\source-data.zip .\.repro-check\source-data-1.zip
Copy-Item .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar .\.repro-check\application-1.jar

Get-FileHash .\.repro-check\source-data-1.zip -Algorithm SHA256
Get-FileHash .\.repro-check\application-1.jar -Algorithm SHA256
~~~

### Bước 2: build sạch lần hai

~~~powershell
.\gradlew.bat --no-build-cache clean packageDocuments bootJar

Copy-Item .\build\distributions\source-data.zip .\.repro-check\source-data-2.zip
Copy-Item .\build\libs\archive-demo-0.0.1-SNAPSHOT.jar .\.repro-check\application-2.jar

Get-FileHash .\.repro-check\source-data-2.zip -Algorithm SHA256
Get-FileHash .\.repro-check\application-2.jar -Algorithm SHA256
~~~

### Bước 3: xác nhận hash bằng nhau và trả lỗi khi khác

~~~powershell
$zip1 = (Get-FileHash .\.repro-check\source-data-1.zip -Algorithm SHA256).Hash
$zip2 = (Get-FileHash .\.repro-check\source-data-2.zip -Algorithm SHA256).Hash
$jar1 = (Get-FileHash .\.repro-check\application-1.jar -Algorithm SHA256).Hash
$jar2 = (Get-FileHash .\.repro-check\application-2.jar -Algorithm SHA256).Hash

if ($zip1 -ne $zip2) { throw "ZIP hash mismatch" }
if ($jar1 -ne $jar2) { throw "JAR hash mismatch" }

Write-Output "ZIP_IDENTICAL"
Write-Output "JAR_IDENTICAL"
~~~

Nếu cả hai phép so sánh pass, output chính xác từ hai câu lệnh cuối là:

~~~text
ZIP_IDENTICAL
JAR_IDENTICAL
~~~

PowerShell hash dạng hex có thể in chữ hoa; chỉ so sánh hai chuỗi cùng do `Get-FileHash` tạo ra, không phụ thuộc vào chữ hoa/thường của SHA-256.

### Về file .repro-check

`.repro-check` nằm **ngoài `build`** để không bị Gradle `clean` xóa. Đừng commit thư mục kiểm thử này vào Git hoặc vô tình thêm nó vào `from('.')` của archive. Nếu project có copy task lấy toàn repo làm input, nên bỏ qua `.repro-check` hoặc đặt artifacts đối chiếu trong một thư mục tạm ngoài project.

## 10. Kiểm tra thứ tự entries và timestamp bên trong archive

### 10.1. Liệt kê thứ tự ZIP/JAR entries

Trên Linux:

~~~bash
jar tf .repro-check/source-data-1.zip
jar tf .repro-check/source-data-2.zip
~~~

Trên PowerShell:

~~~powershell
jar tf .\.repro-check\source-data-1.zip
jar tf .\.repro-check\source-data-2.zip
~~~

So sánh **toàn bộ thứ tự dòng**. Với ZIP mẫu, thông thường hai entry `alpha.txt` và `beta.txt` sẽ xuất hiện trong một thứ tự nhất quán. Nếu archive chứa directory entries thì `jar tf` còn có thể hiện đường dẫn thư mục; đó không nhất thiết là lỗi.

### 10.2. Xem timestamp của entries với JDK

Dùng `jar tvf` thay vì `jar tf`:

~~~bash
jar tvf .repro-check/source-data-1.zip
jar tvf .repro-check/source-data-2.zip
~~~

Lệnh `jar tvf` in dung lượng, timestamp hiển thị và tên entries. **Ngày giờ hiển thị có thể phụ thuộc timezone/locale của công cụ**, nên đừng so chuỗi human-readable giữa các máy khác múi giờ như một thước đo duy nhất. Muốn phân tích chính xác ZIP metadata, dùng công cụ ZIP inspector thích hợp; trong CI nên ưu tiên **SHA-256 byte-for-byte**.

### 10.3. Dùng Python nếu có sẵn để xem ZIP entry metadata

Đây là lệnh kiểm tra **tùy chọn** cần Python 3, không thuộc Gradle core. Linux/bash:

~~~bash
python3 - <<'PY'
from zipfile import ZipFile
path = ".repro-check/source-data-1.zip"
with ZipFile(path) as archive:
    for entry in archive.infolist():
        print(entry.filename, entry.date_time)
PY
~~~

Nó giúp thấy thứ tự entry và tuple thời gian được ZIP lưu cho từng entry. **Không khẳng định timestamp bằng ngày giờ của lần build** khi `preserveFileTimestamps=false`; Gradle cố định metadata phù hợp với định dạng và version Gradle.

### 10.4. Tránh nhầm outer mtime với inner timestamps

Lệnh `stat`/`Get-Item` có thể hiển thị thời gian sửa đổi của `application-1.jar` khác `application-2.jar` vì hai lần copy diễn ra vào thời điểm khác nhau. **Nếu hash SHA-256 bằng nhau**, bytes của archive vẫn giống nhau. Đây là trạng thái reproducible hoàn toàn hợp lệ.

## 11. Áp dụng cho Spring Boot bootJar và bootWar

### 11.1. bootJar là subtype của Jar

Trong Spring Boot Gradle Plugin 3.3, `org.springframework.boot.gradle.tasks.bundling.BootJar` kế thừa `Jar`, vì vậy nó nhận các thuộc tính của `AbstractArchiveTask`. Cấu hình tổng quát:

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

có thể tác động tới `bootJar` trong **project được cấu hình**. Nếu chỉ muốn giới hạn vào executable JAR:

~~~groovy
tasks.named('bootJar') {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Không coi `jar` và `bootJar` là một task**. Java plugin có `jar` thường tạo plain JAR, còn Spring Boot plugin tạo Boot executable JAR với loader và dependencies nằm trong `BOOT-INF/lib`. Project có thể tạo cả hai archive; khi so hash release artifact phải chọn **đúng file `bootJar` đã phát hành**, không chọn file `-plain.jar`.

### 11.2. bootWar là subtype của War

Với project dùng Gradle `war` plugin và Spring Boot plugin, task `bootWar` cũng kế thừa cơ chế archive. Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
}

tasks.named('bootWar') {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Đây là fragment**, không phải project WAR độc lập: để một WAR deployable thực sự cần Servlet application, dependencies và cấu hình `providedRuntime` thích hợp. Ý ở đây chỉ là hai property archive áp dụng cho task `bootWar`. Khi kiểm tra WAR, dùng `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`, không áp công thức `BOOT-INF` của executable JAR.

### 11.3. Embedded/nested dependencies và layers

Spring Boot executable JAR thường chứa nested JARs của dependencies và có thể có `BOOT-INF/layers.idx` hoặc metadata hỗ trợ container image layering. Hai cờ Gradle điều khiển **outer archive entries** và cách Gradle đóng gói, nhưng không thể sửa bytes **bên trong một dependency JAR đã được publish**.

Nếu một SNAPSHOT/changing dependency được build lại với bytes khác dù giữ cùng version, outer Boot JAR sẽ khác SHA-256 một cách đúng đắn. Cần khóa/pin versions, kiểm tra dependency provenance, không cố chỉnh thứ tự file để che sự khác biệt.

Thứ tự dependency entries, metadata layer index và Java build tools có thể thay đổi qua Spring Boot plugin versions. Vì vậy, so sánh artifact cần giữ **cùng plugin version và dependency graph**. `reproducibleFileOrder=true` là điều kiện quan trọng nhưng không phải chứng nhận rằng mọi plugin/generator đã deterministic.

## 12. Bản tương đương Kotlin DSL của project mẫu

Nếu repository sử dụng Kotlin DSL thay cho Groovy, có thể dùng các file thay thế sau.

**settings.gradle.kts:**

~~~kotlin
rootProject.name = "archive-demo"
~~~

**build.gradle.kts:**

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}

springBoot {
    mainClass.set("com.example.archive.ArchiveDemoApplication")
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

tasks.register<Zip>("packageDocuments") {
    from("src/main/archive-data")
    archiveFileName.set("source-data.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
}
~~~

**Lưu ý biên dịch Kotlin DSL:** `Zip` là Gradle task class được cung cấp bởi Gradle Kotlin DSL imports thông dụng. Nếu build script/Gradle version của dự án không tự nhận diện, thêm import `org.gradle.api.tasks.bundling.Zip` ở đầu file; project ví dụ có thể chủ động ghi import này để rõ ràng.

Cùng `ArchiveDemoApplication.java` và hai tệp text, chạy:

~~~bash
./gradlew --no-build-cache clean packageDocuments bootJar
~~~

Kết quả mong muốn giống bản Groovy: một ZIP tài liệu và một Spring Boot executable JAR. **Không giữ cả `settings.gradle`/`settings.gradle.kts` hoặc `build.gradle`/`build.gradle.kts` cùng vai trò trong một project**, chọn một DSL để tránh cấu hình chồng chéo.

## 13. Thêm timestamp tái lập có ý nghĩa: Gradle 9.7+ (nâng cao)

Mặc định `preserveFileTimestamps=false` đủ để loại bỏ timestamp của filesystem. Nếu tổ chức muốn archive entries mang một **timestamp xác định có ý nghĩa**, ví dụ timestamp commit nguồn, Gradle **9.7+** có API incubating `reproducibleFileTimestamp`.

### 13.1. Lấy SOURCE_DATE_EPOCH từ nguồn tin cậy

`SOURCE_DATE_EPOCH` là biến môi trường thường được dùng trong quy trình reproducible builds, biểu diễn **số giây từ Unix epoch**. Có thể lấy từ timestamp commit đã chốt, ví dụ trên Git:

~~~bash
git log -1 --format=%ct
~~~

Đây là cách lấy một giá trị **phụ thuộc vào commit**, ổn định cho những build của cùng commit; nó không phải lúc nào cũng là timestamp chuẩn nghiệp vụ. Trong CI production, nguồn giá trị này phải được xác thực và áp dụng nhất quán.

### 13.2. Groovy DSL (Gradle 9.7+)

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
    reproducibleFileTimestamp = providers.environmentVariable('SOURCE_DATE_EPOCH')
        .map { seconds ->
            java.time.Instant.ofEpochSecond(seconds.toLong()).toEpochMilli()
        }
}
~~~

### 13.3. Kotlin DSL (Gradle 9.7+)

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import java.time.Instant

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    reproducibleFileTimestamp = providers.environmentVariable("SOURCE_DATE_EPOCH")
        .map { Instant.ofEpochSecond(it.toLong()).toEpochMilli() }
}
~~~

**Đây là ví dụ nâng cao theo API 9.7+, không dùng trong project Gradle 8.x ở mục 6.** Nếu project chạy Spring Boot plugin không tương thích Gradle 9.7, **không nâng Gradle chỉ để dùng thuộc tính này**; hai flags thông thường đã xử lý nhu cầu timestamp cố định của archive.

Lưu ý:

- `reproducibleFileTimestamp` được chỉ định bằng **mili-giây**, trong khi `SOURCE_DATE_EPOCH` dùng **giây**. Vì thế phải chuyển bằng `Instant.ofEpochSecond(...).toEpochMilli()`.
- `preserveFileTimestamps` phải là `false`; nếu đặt `true` cùng custom reproducible timestamp, Gradle báo lỗi.
- Ngày giờ ZIP có độ phân giải và khoảng hợp lệ riêng; Gradle có thể nâng timestamp nhỏ hơn minimum, và từ chối timestamp vượt maximum mà format hỗ trợ.
- API `reproducibleFileTimestamp` ở giai đoạn **incubating**; kiểm tra tài liệu Gradle version đang dùng trước khi đưa vào build policy dài hạn.
- Không tạo `SOURCE_DATE_EPOCH` từ `date +%s` tại mỗi lần build nếu mục tiêu là reproducibility giữa các lượt: điều đó chỉ thay timestamp biến động nguồn sang **một timestamp biến động khác**.

## 14. File permissions và các metadata khác

Ngoài entry timestamps và thứ tự file, permission bits có thể khác giữa OS/umask/CI agents. Với Gradle 9.0+, `AbstractArchiveTask` chuẩn hóa permissions mặc định của file và directory entries để hỗ trợ reproducibility.

Nếu project cần cấu hình cố định theo ý định, Gradle phiên bản phù hợp hỗ trợ:

~~~groovy
tasks.named('jar', Jar) {
    preserveFileTimestamps = false
    reproducibleFileOrder = true

    filePermissions {
        unix('644')
    }
    dirPermissions {
        unix('755')
    }
}
~~~

**Đây là trích đoạn chỉ áp dụng cho `jar`**, không tự cấu hình `bootJar`. Trong archive chứa shell scripts hoặc native executables, `644` có thể bỏ quyền executable, vì vậy phải dùng quy tắc riêng cho những entry cần chạy.

**Không đổi file permissions chỉ để làm hash bằng nhau** khi điều đó phá nghĩa của artifact. Thay vì ép permissions bừa, giữ một policy cụ thể cho file thường, thư mục và file executable, rồi xác minh trên môi trường triển khai.

Một số metadata khác có thể làm archive khác bytes dù hai flags đã đúng:

- JAR/WAR manifest có `Implementation-Version`, `Build-Time` hoặc thuộc tính sinh theo clock.
- Spring Boot `build-info.properties` sinh theo task `bootBuildInfo`: metadata `build.time` có thể biến đổi tùy cấu hình/plugin; cần kiểm tra khi dùng.
- Mã Java/Kotlin được compiler phiên bản khác tạo ra các bytes khác.
- Resource filtering chèn hostname, đường dẫn workspace, CI job number hoặc commit metadata khác.
- ZIP entry permissions/owner/group, file encoding/line endings và compression settings thay đổi giữa build tools/OS.
- Dependencies dạng SNAPSHOT/changing hoặc repository trả artifact khác bytes dưới cùng tọa độ.
- Task code generator phụ thuộc thứ tự HashMap iteration, random seed, locale/timezone hoặc network.

**Cách xử lý:** chứng minh component nào khác trước, không tắt lệnh kiểm tra hash hay copy archive phiên bản cũ để “đạt PASS”.

## 15. Troubleshooting: hash khác nhau sau hai clean builds

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| `source-data.zip` khác hash dù alpha/beta không đổi | Archive flags chưa áp dụng đúng task hoặc input file metadata khác | Xem `packageDocuments`, entry order/timestamp, Gradle Wrapper |
| `jar tf` liệt kê cùng files nhưng SHA-256 khác | Entry timestamps, permissions, compression, metadata/manifest hoặc bytes nested JAR | Kiểm tra `jar tvf`, manifest, entries và binary diff |
| `bootJar` khác hash, ZIP dữ liệu lại giống | Generated resources, nested dependencies, loader/plugin version, manifest hoặc class files | So sánh `BOOT-INF/classes`, `BOOT-INF/lib`, Boot plugin/dependency graph |
| Có `reproducibleFileOrder=true` mà hash vẫn khác | Cờ chỉ chuẩn hóa thứ tự một phần sources; nội dung/metadata vẫn volatile | Rà `preserveFileTimestamps`, permissions, generators |
| Có `preserveFileTimestamps=false` nhưng build.time đổi | Timestamp nằm **trong nội dung** generated resource/manifest | Sửa generator, dùng timestamp cố định hoặc không nhúng build time |
| Trên CI Linux hash khác laptop Windows | Line endings, JDK/compiler, files permissions, Gradle/plugin version, normalized input | Cố định Wrapper/toolchain, so sánh nguồn và generated outputs |
| Dùng `--build-cache` thấy hash giống, tắt cache lại khác | Đang khôi phục cùng artifact cũ thay vì tạo deterministic output | Thử `--no-build-cache clean` để kiểm chứng tái tạo thật |
| Đổi `SOURCE_DATE_EPOCH` mà hash đổi | Custom timestamp là một input có ảnh hưởng | Giữ timestamp ổn định với cùng source/commit |
| Gradle báo unknown property `reproducibleFileTimestamp` | Wrapper quá cũ (< Gradle 9.7) | Bỏ API mới; dùng hai Boolean properties hỗ trợ từ lâu |
| Gradle báo lỗi khi dùng custom timestamp | Đặt `preserveFileTimestamps=true` hoặc timestamp vượt range format | Đặt `false`, kiểm tra unit và range timestamp |
| SHA-256 bằng nhau nhưng `ls -l` hiển thị ngày sửa khác | Filesystem mtime của file archive bên ngoài khác | Đây không phải lỗi reproducibility; bytes vẫn bằng nhau |
| `Jar` giống nhưng `bootWar` khác | Chỉ cấu hình task `jar`, không cấu hình `bootWar` | Dùng `AbstractArchiveTask` hoặc cấu hình đúng task deploy |
| Build mất artifact sau `clean` | Bản so sánh trước lưu ngay dưới `build` | Lưu file đầu tiên ở `.repro-check` hoặc thư mục tạm ngoài output |
| Archive contains unexpected entries | CopySpec `from('.')`, tệp tạm, backup, untracked content | Chỉ rõ input directories, không đóng gói cả repository |
| Test CI pass nhưng artifact hash khác | Tests xác minh hành vi chứ không xác minh bytes | Thêm bước compare hash hai clean builds và điều tra diff |
| Tắt `preserveFileTimestamps` phá một logic tool cũ | Tool downstream phụ thuộc mtime của file trong archive | Đánh giá lại requirement, chỉ tạo một artifact riêng hoặc ghi timestamp nghiệp vụ explicit |

### Các bước phân tích khi phát hiện mismatch

1. Ghi SHA-256 của hai archive và version `./gradlew --version`.
2. Dùng `jar tf` để diff danh sách và **thứ tự entry**, `jar tvf` để kiểm tra timestamp.
3. Nếu entry list giống, giải nén mỗi archive vào thư mục riêng và diff **file contents**; nếu contents trùng, tập trung vào metadata/compression.
4. Đọc `META-INF/MANIFEST.MF` và generated resources như `build-info.properties`.
5. Với Boot JAR, so sánh danh sách `BOOT-INF/lib` và SHA-256 của nested JARs nếu cần; đừng coi tất cả các dependencies đã được cố định chỉ vì tên file giống.
6. So sánh toolchain, Gradle Wrapper, compiler flags, locale, encoding, input line endings và permissions.
7. Khi tìm ra nguồn khác biệt, sửa **ở source of truth** (build script, generator, dependency management, CI environment), không chỉnh sửa JAR sau build một cách thủ công.
8. Chạy lại **hai clean builds không dùng cache** và so hash.

## 16. Reproducibility, Build Cache và supply-chain: quan hệ nhưng không đồng nhất

| Cơ chế | Mục tiêu | Vì sao liên quan? |
| --- | --- | --- |
| Reproducible archives | Cùng input → cùng bytes trong ZIP/JAR/WAR | Cho phép so sánh artifact hash |
| Gradle Build Cache | Tái sử dụng outputs của task cacheable theo inputs/cache key | Output deterministic giúp cache entries đáng tin và giảm downstream invalidation |
| Up-to-date checks | Bỏ qua task khi inputs/outputs trong workspace còn hợp lệ | Không chứng minh có thể tái tạo cùng bytes ở máy khác |
| Dependency verification/locking | Kiểm tra/ổn định module và version resolve | Giảm nguy cơ same source nhưng kéo dependencies khác |
| SBOM/provenance/attestations | Ghi nhận nguồn gốc và thành phần artifact | Hash reproducible là bằng chứng hữu ích, nhưng không tự chứng minh nguồn code an toàn |
| CI artifact retention | Giữ bản đã build để triển khai đúng thứ đã test | Tránh rebuild với inputs hoặc môi trường chưa được kiểm soát |

**Không nhận một build cache hit là bằng chứng reproducibility**: nếu task được load từ cache, bạn có thể đang so cùng byte stream do một lượt build trước tạo ra. Thử `--no-build-cache clean` hoặc một môi trường độc lập là cách xác minh tốt hơn.

**SHA-256 bằng nhau cũng không chứng minh artifact không chứa lỗ hổng**: nó chứng minh hai file có cùng bytes với xác suất va chạm bỏ qua trong bối cảnh thực tế. Cần thêm dependency scanning, test, signing, permissions và provenance phù hợp.

### Vì sao giúp container images?

Spring Boot JAR có thể được đưa vào container image như một file hoặc phân thành layers. Nếu mỗi lượt build tạo JAR khác hash do metadata vô hại, Docker/OCI image layers và build caches có thể bị invalidated dù source chức năng không đổi. Archive có bytes ổn định làm caching và artifact auditing dễ đoán hơn.

**Không tự suy ra image digest sẽ bằng nhau chỉ vì JAR hash bằng nhau**: Dockerfile, base image digest, layer metadata, timestamps, build arguments và image tooling cũng có thể thay đổi.

## 17. Một kiểm tra reproducibility cho CI — script bash an toàn

Nếu tổ chức yêu cầu xác minh hai bản build của cùng commit có cùng SHA-256, script sau minh họa **phép so sánh trên cùng CI worker**. Nên dùng container/JDK/Gradle Wrapper đã được pin, và tách bước kiểm thử chức năng khỏi bước reproducibility.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

./gradlew --no-build-cache clean packageDocuments bootJar

mkdir -p .repro-check
cp build/distributions/source-data.zip .repro-check/source-1.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/app-1.jar

./gradlew --no-build-cache clean packageDocuments bootJar

cp build/distributions/source-data.zip .repro-check/source-2.zip
cp build/libs/archive-demo-0.0.1-SNAPSHOT.jar .repro-check/app-2.jar

sha256sum .repro-check/source-1.zip .repro-check/source-2.zip
sha256sum .repro-check/app-1.jar .repro-check/app-2.jar

cmp .repro-check/source-1.zip .repro-check/source-2.zip
cmp .repro-check/app-1.jar .repro-check/app-2.jar

echo "REPRODUCIBLE_ARCHIVES_PASS"
~~~

Nếu tất cả các lệnh `cmp` xác nhận bytes giống, output **cuối cùng do script in ra** là:

~~~text
REPRODUCIBLE_ARCHIVES_PASS
~~~

Nếu ZIP hoặc JAR khác, `cmp` trả exit code khác 0 và `set -e` khiến script dừng trước khi in PASS. Tránh lệnh `cmp || true` hoặc nuốt exit code; CI cần thất bại rõ ràng.

**Đây chỉ là kiểm tra trên cùng worker**. Kiểm chứng mạnh hơn cần chạy ở **hai workspace hoặc hai máy độc lập** từ cùng commit, cùng công cụ được kiểm soát, rồi trao đổi hash/artifact để đối chiếu. Khi thực hiện phép kiểm tra cross-OS, cần lưu ý cả compiler/encoding/path normalization chứ không chỉ archive flags.

Không nên mặc định hai lần build nặng liên tiếp trong mọi PR nếu chi phí quá lớn; có thể dùng một job định kỳ, release gate hoặc cơ chế kiểm tra theo policy tổ chức. Dù vậy, đối với artifact phát hành có yêu cầu provenance mạnh, phải có bằng chứng phù hợp thay vì chỉ tin flags.

## 18. Những hiểu nhầm thường gặp

| Nhận định | Thực tế |
| --- | --- |
| “Gradle luôn cần tự cấu hình `preserveFileTimestamps=false`.” | Từ **Gradle 9.0**, thuộc tính này mặc định `false` cho `AbstractArchiveTask`; Gradle cũ hơn cần kiểm tra/cấu hình. |
| “Chỉ đặt `reproducibleFileOrder=true` là đủ.” | Timestamp, permissions, generator output và dependencies còn có thể biến động. |
| “Tắt preserve timestamps làm mất lịch sử Git.” | Nó chỉ thay **timestamp entries trong archive**, không xóa commit history hoặc sửa mtime file nguồn. |
| “File .jar có filesystem mtime khác nên không reproducible.” | Outer mtime có thể khác trong khi **bytes archive và SHA-256 giống nhau**. |
| “Hash bằng nhau sau `--build-cache` chứng minh tự build lại ổn định.” | Có thể chỉ khôi phục cùng output từ cache; kiểm tra bằng `--no-build-cache clean`. |
| “`jar tf` có cùng tên file nghĩa SHA-256 chắc chắn giống.” | Entry order, timestamps, permissions, compression hoặc nội dung nested JAR còn có thể khác. |
| “Cấu hình `jar` cũng tự cấu hình `bootJar`.” | Đây là các task khác nhau, dù `bootJar` kế thừa loại `Jar`. |
| “Cấu hình archive sửa được timestamp nằm trong `build-info.properties`.” | Không; đó là **nội dung file**, phải sửa generator/config nguồn. |
| “Có `reproducibleFileTimestamp` trong mọi Gradle version.” | Thuộc tính mới có từ **Gradle 9.7**; project 8.x không được dùng. |
| “Hash bằng nhau tự chứng minh image/SBOM an toàn.” | Còn cần kiểm tra dependency/provenance/scanning và các layers khác. |

## 19. Checklist và bài thực hành

Làm trong một branch thử nghiệm của Spring Boot Gradle project có Java 17+:

1. Kiểm tra `./gradlew --version`, Java toolchain và Spring Boot plugin version. Xác định Gradle ở trước hay sau **9.0**.
2. Với Gradle 8.x hoặc khi muốn policy hiển thị rõ, thêm hai flags trên `AbstractArchiveTask`: `preserveFileTimestamps=false`, `reproducibleFileOrder=true`.
3. Tạo source ZIP `alpha.txt`/`beta.txt` và project Spring Boot `ArchiveDemoApplication` đúng ví dụ.
4. Chạy `--no-build-cache clean packageDocuments bootJar`, mở archive bằng `jar tf`, xác định đúng Boot executable JAR.
5. Lưu artifact thứ nhất ở `.repro-check` ngoài thư mục `build`.
6. Build lại bằng cùng command, không sửa source/Gradle config/dependency, lưu artifact thứ hai.
7. Dùng `sha256sum` hoặc `Get-FileHash` và `cmp`/PowerShell assert để kiểm tra **hai archive có bytes giống nhau**.
8. Nếu mismatch, kiểm tra lần lượt entry order, timestamps, manifest, permissions, generated files, bytecode, nested dependencies và toolchain.
9. Chạy `java -jar` để bảo đảm Boot executable JAR vẫn hoạt động sau khi chuẩn hóa metadata.
10. Kiểm tra một **thay đổi có thật** (ví dụ đổi `alpha.txt` thành nội dung khác), build lại và xác nhận ZIP hash đổi; đây là điều đúng, không phải lỗi reproducibility.
11. Khôi phục nội dung gốc và xác minh hash baseline có thể tái tạo.
12. Ghi lại kết quả trong PR/CI: Gradle/JDK/Boot versions, lệnh, SHA-256 lần 1/2, file artifact và nguyên nhân nếu khác.
13. Nếu dùng remote build cache hoặc configuration cache, xác định chúng là tối ưu **riêng**; không lấy trạng thái cache làm bằng chứng duy nhất.
14. Với Gradle 9.7+ và policy riêng, đánh giá `SOURCE_DATE_EPOCH` có thật sự cần thiết và có giữ ổn định giữa các builds không.

**Đạt yêu cầu khi:** bạn giải thích được vì sao ZIP/JAR thay hash dù nội dung logic giống nhau; cấu hình được `AbstractArchiveTask` bằng Groovy hoặc Kotlin DSL; chứng minh hai clean builds cùng source có **SHA-256 giống nhau**; và nêu được các giới hạn của hai archive flags.

## Tài liệu chính thức và đọc thêm

- [Gradle – Working with Files: Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle – AbstractArchiveTask DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle – Upgrade to Gradle 9.0: Reproducible Archives Defaults](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html)
- [Gradle – Solving Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html)
- [Gradle – Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html)
- [Gradle – Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Gradle – Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – BootJar API](https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootJar.html)
- [Reproducible Builds – JVM](https://reproducible-builds.org/docs/jvm/)
