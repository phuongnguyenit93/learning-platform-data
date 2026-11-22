# Tái tạo gói cài đặt khi thư viện hoặc Java runtime cần bản vá

## 1. Vấn đề: cập nhật source chưa có nghĩa máy khách đã được vá

Ứng dụng Java được đóng gói bằng **`jpackage`** thường mang theo **mã ứng dụng**, các **JAR phụ thuộc**, **native launcher** và một **Java runtime image** trong cùng application image. Installer native (`.msi`/`.exe`, `.deb`/`.rpm` hoặc `.pkg`/`.dmg`) có thể được tạo từ image này để cài đặt trên hệ điều hành tương ứng.

Khi một thư viện có lỗi được sửa hoặc Java runtime có security update, **không thể chỉ cập nhật `pom.xml`, `build.gradle` hoặc JDK cài trên máy phát triển rồi mặc định người dùng đã được bảo vệ**. Máy khách vẫn có thể dùng những byte cũ bên trong package đã phát hành.

**Quy trình đúng:** xác định bản vá cần thiết → chọn artifact/JDK đã sửa → build ứng dụng và dependencies → chuẩn bị staging sạch → tạo lại application image → xác minh launcher + runtime + dependency → tạo lại installer → kiểm thử nâng cấp/rollback → ký và phát hành bản mới.

Bài này thuộc nhóm **Gói cài đặt** của module Java 14. `jpackage` đã trở thành công cụ chính thức trong **JDK 16 (JEP 392)** và vẫn được duy trì ở các JDK hiện đại. Ví dụ Java dùng **Java 17+**, không dùng preview/incubator hay hướng dẫn legacy. Các phiên bản số trong bài học chỉ là **ví dụ giả lập**; một release bảo mật thực tế phải được xác minh theo advisory và bản build của nhà cung cấp.

### Mục tiêu học tập

- Biết **vì sao phải tái tạo gói** khi dependency hoặc runtime đóng kèm thay đổi.
- Phân biệt `app.jar`, dependency JAR, custom runtime, application image, installer và dữ liệu người dùng.
- Biết thao tác build lại bằng `javac`, `jar`, `jlink` và `jpackage` theo đúng vai trò.
- Có cách kiểm tra **thư viện và JDK thực sự nằm trong gói mới**, không chỉ trong source repo.
- Hiểu versioning, nhận dạng nâng cấp của Windows/Linux/macOS, chữ ký, SBOM và rollback.
- Chạy được một ví dụ Java 17+ tạo **hai app image** chứa hai phiên bản thư viện khác nhau.

## 2. Các tầng artifact có thể mang thành phần cũ

~~~text
           Mã nguồn + cấu hình build
                     |
                     v
          Resolve dependency versions
                     |
                     v
          Build / Tests / Main JAR
                     |
                     v
          Clean staging --input folder
          (app.jar + library*.jar + files)
                     |
                 jpackage
                     |
       +-------------+--------------+
       |                            |
       v                            v
 JAR payload                 Java runtime image
 (ứng dụng + lib)         (jlink hoặc --runtime-image)
       |                            |
       +-------------+--------------+
                     |
                     v
              Application image
         (launcher + app + runtime)
                     |
                     v
           Native installer/package
                     |
                     v
          Cài đặt/nâng cấp tại máy khách
~~~

| Thành phần | Nằm ở đâu? | Cần làm khi vá? |
|---|---|---|
| Main JAR | Payload ứng dụng trong `--input` | Build mới nếu source/dependency interface thay đổi; xác minh main class |
| Runtime dependency JAR | `--input` hoặc đóng trong fat JAR | Chọn phiên bản đã sửa, copy/build lại và kiểm tra không còn bản cũ |
| Java runtime đóng kèm | Runtime trong app image | Dùng patched JDK để tạo runtime mới hoặc cung cấp custom runtime mới |
| Native launcher | Thành phần OS-specific do `jpackage` tạo | Tạo image mới và chạy smoke test |
| Native installer | `msi/exe/deb/rpm/pkg/dmg` | Tạo lại từ image đã kiểm tra, quản lý version và upgrade identity |
| User data | Cấu hình, database, hồ sơ người dùng | Bảo toàn qua upgrade; đặt ngoài thư mục có thể bị installer thay thế |

**Điểm cốt lõi:** cập nhật một trong các tầng đầu vào **không tự thay đổi artifact đã phát hành**. Bất kỳ báo cáo nào nói “đã vá” phải nói rõ **gói nào**, **version nào**, **đã kiểm tra những byte nào** và **đã được cài trên những thiết bị nào**.

## 3. Khi dependency/library cần bản vá

### 3.1. Xác định đúng thư viện và phiên bản được sửa

Khi phát hiện lỗ hổng, hãy đối chiếu nguồn đáng tin cậy:

1. **Tên artifact và tọa độ** (Maven group/artifact/version nếu có).
2. Version bị ảnh hưởng và **version/build đã sửa** theo security advisory.
3. Lỗ hổng có thể được kích hoạt trong cách ứng dụng thực sự sử dụng thư viện không.
4. Thư viện là **direct dependency**, **transitive dependency**, nested JAR trong fat JAR, hay được copy thủ công vào folder.
5. Thay đổi API/ABI có làm ứng dụng cần sửa source/recompile hoặc migrate dữ liệu không.
6. Có nhiều bản của cùng thư viện trên classpath hoặc trong image không.

Không dùng quy tắc “version cao hơn luôn an toàn hơn” thay cho advisory: có thể bản mới chưa sửa đúng lỗi, hoặc một nhánh được hỗ trợ có bản vá backport riêng.

### 3.2. Cập nhật dependency và build lại

Với Maven/Gradle, sau khi thay dependency version trong build config hoặc lockfile, chạy dependency inventory và test phù hợp.

Ví dụ Maven:

~~~bash
mvn dependency:tree
mvn clean verify
~~~

Ví dụ Gradle Wrapper trên Linux/macOS:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean test jar
~~~

**Các lệnh này chỉ minh họa**, cần project có plugin/task tương ứng và quyền truy cập dependency repository. Chúng không mặc nhiên chuẩn bị đủ bộ `--input` cho `jpackage`; pipeline thường có bước tạo distribution/staging riêng.

**Không chỉ xem `pom.xml` hoặc `build.gradle`.** Hãy kiểm tra **runtimeClasspath đã resolve**, SBOM và những file thực sự nằm trong app image. Một fat JAR hoặc file dependency copy sẵn có thể còn chứa bản cũ dù build configuration đã cập nhật.

### 3.3. Dùng staging folder mới cho mỗi release

Ví dụ:

~~~text
release-1.0.1/
├── stage/
│   ├── app.jar
│   ├── dependency-fixed.jar
│   └── assets/
└── out/
    └── PatchDemo/  (app image)
~~~

`stage` là đầu vào `--input`, còn `out` là `--dest`. Đừng đặt output bên trong input; đừng dùng toàn bộ project root làm input vì có thể đưa source, test data, cache hoặc secrets vào installer.

**Vì sao nên dọn sạch?** Nếu cùng có `dependency-1.0.0.jar` và `dependency-1.0.1.jar` trong payload, launcher có thể nạp bản không mong muốn hoặc tạo xung đột classpath. Cách an toàn là **build staging sạch với những JAR đã duyệt**, không chỉ chép thêm file mới.

### 3.4. Tại sao không sửa JAR trực tiếp trong thư mục cài đặt?

Việc thay `library.jar` thủ công trong image đang dùng không bảo đảm:

- Launcher thực sự nạp đúng file vừa thay.
- Không còn bản cũ trong fat JAR, cache hoặc thư mục phụ.
- Chữ ký và hash của image/installer vẫn hợp lệ.
- Hệ thống quản lý package không khôi phục file cũ ở lần repair/update sau.
- Có cách rollback và truy vết version được cài.

Với ứng dụng `jpackage` thông thường, **tái tạo image/installer từ staging sạch** là con đường phát hành mặc định. Các hệ thống cập nhật delta/hotpatch riêng cần cơ chế ký, xác thực, giao dịch, rollback và hỗ trợ rõ ràng; `jpackage` một mình không cung cấp hệ thống tự vá JAR đang cài.

## 4. Khi Java runtime cần bản vá

### 4.1. Runtime đóng kèm không tự nhận update từ hệ điều hành

Một **self-contained application image** có Java runtime của riêng nó. Người dùng cập nhật JDK trong `PATH` hoặc `JAVA_HOME` không có nghĩa launcher sẽ chuyển sang JDK đó.

Theo tài liệu `jpackage`:

- Nếu **không** truyền `--runtime-image`, `jpackage` dùng **`jlink`** để tạo runtime từ JDK/cấu hình packaging.
- Nếu truyền `--runtime-image <directory>`, công cụ **copy runtime image đã chỉ định** vào application image.
- Một runtime image đã tạo từ bản JDK cũ **vẫn là bản cũ** sau khi môi trường build cài JDK mới, nếu không tạo lại nó.

Khi có JDK security update, phải chọn patched JDK hợp lệ, **rebuild Java runtime image** rồi rebuild app image/installer. Không sửa mỗi dòng version trong file metadata.

### 4.2. Phân biệt compiler target và runtime version

~~~bash
javac --release 17 -d classes src/org/example/app/Main.java
~~~

`--release 17` kiểm soát cú pháp/API và bytecode target **Java 17**. Nó **không ép runtime trong app image là Java 17**. Nếu chạy `jpackage` bằng JDK khác, runtime thường lấy từ JDK dùng packaging, trừ khi đã chỉ định `--runtime-image`.

Trong bài thử thực tế, mã Java được biên dịch bằng `--release 17` nhưng runtime đóng kèm do `jpackage` của **JDK 24.0.2** tạo có metadata:

~~~text
JAVA_VERSION="24.0.2"
~~~

Đây là **kết quả máy thử**, không phải khuyến nghị rằng JDK 24.0.2 hiện là bản vá mới nhất hay bản phù hợp cho phát hành. Trong production, hãy chọn nhánh JDK được vendor hỗ trợ và bản build đáp ứng advisory, rồi đọc version **từ image cuối**.

### 4.3. Kiểm tra runtime đi kèm, không kiểm tra nhầm JDK của host

Trên Windows, layout app image thông thường có `runtime/release`:

~~~powershell
Select-String -Path .\dist\PatchDemo\runtime\release -Pattern '^JAVA_VERSION='
~~~

Trên Linux, layout app image có thể đặt runtime dưới `lib/runtime/release`:

~~~bash
grep '^JAVA_VERSION=' dist/PatchDemo/lib/runtime/release
~~~

Đường dẫn là **ví dụ**, cần xác nhận layout thực tế của OS/JDK đang dùng. `release` chứa version runtime image. Để chứng minh bản vá đã có, còn phải đối chiếu **vendor build/security advisory**, các module và kiểm thử thực tế. Đừng chỉ nhìn text version mà suy ra mọi CVE đã được khắc phục.

### 4.4. Custom runtime tạo bằng jlink

Ví dụ **minh họa** trên Bash:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging --output runtime-patched
jpackage --type app-image --name Demo --input stage --main-jar app.jar --runtime-image runtime-patched --dest dist
~~~

Danh sách module trong ví dụ **không nhất thiết đủ** cho ứng dụng thật. Khi vá runtime, phải chạy lại `jlink` bằng JDK đã vá, bảo đảm đủ `java.sql`, `java.desktop`, TLS/crypto providers, native libraries hoặc những module khác mà app thực sự cần. Không chỉ dùng lại thư mục `runtime-patched` cũ vì tên của nó có chữ “patched”.

**Điểm cần cập nhật ở JDK mới:** từ **JDK 25**, `jpackage` không còn mặc định thêm service bindings vào runtime image do nó tạo, khác các JDK trước đó. Nếu ứng dụng dựa vào `ServiceLoader`/provider modules, hãy kiểm tra module graph khi đổi JDK. Chỉ thêm `--jlink-options` và `--bind-services` theo tài liệu đúng JDK khi có nhu cầu, không copy nguyên cờ cũ mà không thử nghiệm.

### 4.5. Không tự ý nâng major version

Bản vá có thể đến từ một nhánh JDK đang được hỗ trợ mà không yêu cầu nâng major. Chọn theo vendor support/security advisory và policy ứng dụng. Nâng major version cần kiểm thử thêm module access, runtime behavior, compatibility, service providers, TLS, locale/timezone và native integration. Nhưng cũng không nên giữ một runtime đã hết hỗ trợ khi không còn cách nhận bản vá cần thiết.

## 5. Tạo app image mới và tạo installer mới

### 5.1. Image mới từ staging đã vá

Ví dụ PowerShell trên Windows:

~~~powershell
jpackage --type app-image --name PatchDemo --app-version 1.0.1 --input .\stage-patched --main-jar app.jar --main-class org.example.app.Main --dest .\dist --win-console
~~~

Lệnh là **ví dụ**: giả định `stage-patched` đã có main JAR và dependency đúng, công cụ `jpackage` của JDK bạn đã chọn có sẵn.

Nếu dùng runtime đã tự tạo:

~~~powershell
jpackage --type app-image --name PatchDemo --app-version 1.0.1 --input .\stage-patched --main-jar app.jar --main-class org.example.app.Main --runtime-image .\runtime-patched --dest .\dist --win-console
~~~

Ở đây `--runtime-image` được chọn **khi tạo app image**. Thư mục runtime phải là image hợp lệ, đúng OS/architecture.

### 5.2. Installer mới từ app image đã kiểm chứng

Sau khi chạy smoke test image mới, có thể dùng nó để tạo installer:

~~~powershell
jpackage --type msi --name PatchDemo --app-image .\dist\PatchDemo --dest .\installers
~~~

Đây là **ví dụ Windows** chưa chạy trong bài thử; việc tạo MSI cần công cụ Windows installer phù hợp, thường gồm WiX. Trên Linux có `deb/rpm`, trên macOS có `pkg/dmg`, với điều kiện toolchain tương ứng.

**Giới hạn quan trọng:** Không truyền đồng thời `--app-image` và `--runtime-image` trong bước tạo installer từ image có sẵn. Tài liệu Oracle nêu rõ hai lựa chọn xung đột ở đây. Nếu cần vá Java runtime, **phải xây image mới bằng runtime mới trước**, không đợi đến bước tạo installer rồi thêm `--runtime-image`.

### 5.3. Bảng phân biệt tùy chọn

| Tùy chọn | Trỏ tới | Thời điểm dùng |
|---|---|---|
| `--input` | Thư mục chứa JAR/resource payload | Khi tạo image cho ứng dụng non-modular |
| `--main-jar` | Main JAR tương đối với input | Khi tạo launcher classpath |
| `--main-class` | Fully qualified main class | Khi manifest chưa đủ hoặc muốn chỉ rõ main |
| `--runtime-image` | Runtime image đã có | Khi cần runtime custom/đã vá lúc xây image |
| `--type app-image` | Loại output app image | Khi muốn tạo image mới |
| `--app-image` | Application image đã có | Khi tạo installer từ image đó |
| `--app-version` | Version ứng dụng/package | Khi phát hành version mới |
| `--dest` | Thư mục kết quả | Khi xuất image hoặc installer |

**Đừng nhầm `--type app-image` với `--app-image`**: một cái chọn loại output cần tạo, một cái nhận image đã tồn tại làm input.

## 6. Quản lý phiên bản và danh tính nâng cấp theo hệ điều hành

Bản vá thư viện dù không thêm tính năng mới vẫn phải có **app/package version mới** để người dùng và hệ thống quản lý package phân biệt bản cũ/bản đã sửa. Ví dụ:

~~~text
Ứng dụng:       PatchDemo 1.0.0 -> PatchDemo 1.0.1
Thư viện:       library 1.0.0 -> library 1.0.1
Java runtime:   kiểm chứng riêng theo JDK vendor/build
~~~

Ba version này **không phải một**. `--app-version 1.0.1` không chỉ định phiên bản JDK. Chữ số thư viện ở ví dụ không nói rằng đã có bản vá CVE thật.

### Windows

`jpackage` hỗ trợ `--win-upgrade-uuid` cho các gói liên quan nâng cấp. Trong pipeline Windows, hãy giữ **UUID nâng cấp ổn định cho cùng một dòng sản phẩm**, tăng `--app-version` phù hợp và kiểm thử đường nâng cấp từ installer đã phát hành. Không phát sinh UUID ngẫu nhiên mới mỗi lần build rồi mặc định MSI/EXE sẽ nhận đây là bản update của cùng ứng dụng.

`--win-update-url` chỉ cung cấp URL thông tin update; **nó không tự trở thành cơ chế tải/xác thực/cài đặt bản vá hoàn chỉnh**. Cần kênh cập nhật/triển khai riêng và chính sách rollback.

### Linux

Để package manager coi bản mới là bản nâng cấp cùng ứng dụng, cần giữ **package identity** nhất quán; tùy trường hợp dùng `--linux-package-name`, `--app-version` và `--linux-app-release` (release/revision trong `rpm/deb`). Thử nâng cấp trên bản phân phối đích và giữ đúng dependency metadata.

### macOS

Với `.app`/`pkg`/`dmg`, giữ **bundle/package identifier** hợp lý và ổn định (ví dụ `--mac-package-identifier`), sử dụng version thích hợp, và **ký lại** sau khi thay JAR/runtime. Nếu quy trình phân phối yêu cầu Apple notarization, cần thực hiện theo chính sách của kênh phát hành. Bản `.dmg` mới có cùng tên không tự đảm bảo đã nâng cấp thành công app cũ.

### OS-specific

`jpackage` tạo native launcher/installer theo OS nơi chạy. Không đóng một `.exe` trên Windows rồi sao chép sang Linux mong nó hoạt động. Build và smoke test riêng cho OS/architecture được hỗ trợ.

## 7. Chương trình Java 17+ minh họa thay thư viện

Ví dụ dưới đây **không giả lập lỗ hổng bảo mật**. Nó thay một thư viện nhỏ giữ nguyên API nhưng thay giá trị version, rồi **tạo hai app image khác nhau** để chứng minh image mới chứa byte thư viện mới.

### 7.1. Thư viện VersionInfo.java

Lưu tại `libsrc/org/example/lib/VersionInfo.java`:

~~~java
package org.example.lib;

public final class VersionInfo {
    private VersionInfo() {}

    public static String label() {
        return "1.0.0";
    }
}
~~~

Version mới sẽ dùng giá trị `"1.0.1"`. Đây là thay đổi implementation đơn giản; API `label()` giữ nguyên nên JAR app không phải đổi trong demo. Với thay đổi dependency thực tế, có thể cần recompile app và test nhiều hơn.

### 7.2. Ứng dụng Main.java

Lưu tại `appsrc/org/example/app/Main.java`:

~~~java
package org.example.app;

import org.example.lib.VersionInfo;

public class Main {
    public static void main(String[] args) {
        System.out.println("library=" + VersionInfo.label());
        System.out.println("launcher=ok");
    }
}
~~~

Main JAR chứa `org.example.app.Main`, phụ thuộc `org.example.lib.VersionInfo` nên cả `app.jar` và `library.jar` phải nằm trong staging.

### 7.3. Script PowerShell hoàn chỉnh (Windows)

Script dùng các thư mục tạm riêng, tạo hai thư viện, một main JAR, hai app image, chạy launcher của mỗi image, so sánh SHA-256 JAR và đọc `runtime/release`. Sau khi chạy, tất cả file QA tạm được xóa. **Cần có `javac`, `jar`, `jpackage` trong PATH và quyền ghi `$env:TEMP`**.

~~~powershell
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:TEMP ('jpackage-patch-qa-' + [Guid]::NewGuid().ToString('N'))
$libSrc = Join-Path $root 'libsrc\org\example\lib'
$appSrc = Join-Path $root 'appsrc\org\example\app'
$appClasses = Join-Path $root 'appclasses'
$lib1Classes = Join-Path $root 'lib1classes'
$lib2Classes = Join-Path $root 'lib2classes'
$stage1 = Join-Path $root 'stage1'
$stage2 = Join-Path $root 'stage2'
$dest1 = Join-Path $root 'out1'
$dest2 = Join-Path $root 'out2'
New-Item -ItemType Directory -Path $libSrc,$appSrc,$appClasses,$lib1Classes,$lib2Classes,$stage1,$stage2,$dest1,$dest2 -Force | Out-Null

try {
    $libCode = @'
package org.example.lib;
public final class VersionInfo {
    private VersionInfo() {}
    public static String label() {
        return "1.0.0";
    }
}
'@
    $appCode = @'
package org.example.app;
import org.example.lib.VersionInfo;
public class Main {
    public static void main(String[] args) {
        System.out.println("library=" + VersionInfo.label());
        System.out.println("launcher=ok");
    }
}
'@
    $libFile = Join-Path $libSrc 'VersionInfo.java'
    $appFile = Join-Path $appSrc 'Main.java'
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($libFile, $libCode, $utf8)
    [IO.File]::WriteAllText($appFile, $appCode, $utf8)

    & javac --release 17 -d $lib1Classes $libFile
    if ($LASTEXITCODE -ne 0) { throw 'library v1 compile failed' }
    & jar --create --file (Join-Path $stage1 'library.jar') -C $lib1Classes .
    if ($LASTEXITCODE -ne 0) { throw 'library v1 jar failed' }
    & javac --release 17 -cp (Join-Path $stage1 'library.jar') -d $appClasses $appFile
    if ($LASTEXITCODE -ne 0) { throw 'app compile failed' }
    & jar --create --file (Join-Path $stage1 'app.jar') --main-class org.example.app.Main -C $appClasses .
    if ($LASTEXITCODE -ne 0) { throw 'app jar failed' }
    & jpackage --type app-image --name PatchDemo --app-version 1.0.0 --input $stage1 --main-jar app.jar --main-class org.example.app.Main --dest $dest1 --win-console
    if ($LASTEXITCODE -ne 0) { throw 'image v1 build failed' }

    Write-Output 'BEFORE_PATCH'
    & (Join-Path $dest1 'PatchDemo\PatchDemo.exe')
    if ($LASTEXITCODE -ne 0) { throw 'image v1 launcher failed' }

    $libCode = $libCode.Replace('"1.0.0"','"1.0.1"')
    [IO.File]::WriteAllText($libFile, $libCode, $utf8)
    & javac --release 17 -d $lib2Classes $libFile
    if ($LASTEXITCODE -ne 0) { throw 'library v2 compile failed' }
    & jar --create --file (Join-Path $stage2 'library.jar') -C $lib2Classes .
    if ($LASTEXITCODE -ne 0) { throw 'library v2 jar failed' }
    Copy-Item -LiteralPath (Join-Path $stage1 'app.jar') -Destination (Join-Path $stage2 'app.jar')
    & jpackage --type app-image --name PatchDemo --app-version 1.0.1 --input $stage2 --main-jar app.jar --main-class org.example.app.Main --dest $dest2 --win-console
    if ($LASTEXITCODE -ne 0) { throw 'image v2 build failed' }

    Write-Output 'AFTER_PATCH'
    & (Join-Path $dest2 'PatchDemo\PatchDemo.exe')
    if ($LASTEXITCODE -ne 0) { throw 'image v2 launcher failed' }

    $oldHash = (Get-FileHash (Join-Path $stage1 'library.jar')).Hash
    $newHash = (Get-FileHash (Join-Path $stage2 'library.jar')).Hash
    Write-Output ('PATCHED_JAR_HASH_CHANGED=' + ($oldHash -ne $newHash))
    $releaseFile = Join-Path $dest2 'PatchDemo\runtime\release'
    if (Test-Path -LiteralPath $releaseFile) {
        $line = Get-Content -LiteralPath $releaseFile | Where-Object { $_ -match '^JAVA_VERSION=' } | Select-Object -First 1
        Write-Output ('BUNDLED_RUNTIME_RELEASE=' + $line)
    } else {
        Write-Output 'BUNDLED_RUNTIME_RELEASE=not-found'
    }
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
~~~

Script này có mỗi lệnh chạy riêng trên một dòng, **không phụ thuộc PowerShell line continuation**. Trình biên dịch dùng `--release 17`. `jpackage` tạo image **Windows**, không phải MSI; mục tiêu của ví dụ là xác nhận bộ thư viện đã được thay đúng khi rebuild.

### 7.4. Kết quả stdout đã chạy thử thực tế

Trên máy kiểm thử dùng JDK 24.0.2 cho `jpackage`:

~~~text
BEFORE_PATCH
library=1.0.0
launcher=ok
AFTER_PATCH
library=1.0.1
launcher=ok
PATCHED_JAR_HASH_CHANGED=True
BUNDLED_RUNTIME_RELEASE=JAVA_VERSION="24.0.2"
~~~

**Lưu ý:** Dòng `BUNDLED_RUNTIME_RELEASE` phụ thuộc JDK và layout image của máy chạy. Trong môi trường khác, version có thể khác hoặc script có thể in `not-found` nếu vị trí file `release` khác. Các dòng còn lại xác nhận hai JAR và hai launcher có hành vi khác nhau sau khi thay library trong demo.

### 7.5. Phân tích từng bằng chứng

1. `BEFORE_PATCH` và `library=1.0.0`: image thứ nhất thật sự nạp thư viện ban đầu.
2. `AFTER_PATCH` và `library=1.0.1`: image thứ hai nạp thư viện được build lại trong staging khác.
3. `PATCHED_JAR_HASH_CHANGED=True`: byte của hai thư viện khác nhau. **Hash khác không tự chứng minh một CVE đã được vá**.
4. `BUNDLED_RUNTIME_RELEASE=...`: đọc metadata từ runtime **trong image mới**, không phải output `java -version` của host.
5. Hai image đều dùng JDK packaging giống nhau: ví dụ chứng minh **vá thư viện**, không giả vờ đã vá JDK. Nếu cần vá JDK thì phải chọn build mới và lặp lại quy trình `jpackage/jlink`.

**Trong sản phẩm thật, không áp dụng việc copy nguyên app.jar như mặc định** nếu bản library mới thay đổi API/ABI, thay đổi behavior hoặc yêu cầu bản build khác. Nên build/test lại toàn ứng dụng, đặc biệt khi có dependency transitive.

## 8. Kiểm chứng trên artifact cuối

Chỉ kiểm tra code hoặc dependency lockfile chưa đủ. Để khẳng định installer thực sự chứa bản vá, nên có ma trận kiểm tra:

| Mục | Cách xác minh | Điều không đủ |
|---|---|---|
| Dependency đã cập nhật | SBOM, runtime classpath, JAR hash/version bên trong image | Chỉ nhìn version trong `pom.xml` |
| Bản JAR cũ đã được loại | Kiểm tra staging + image, fat JAR và dependency trùng | Chỉ xóa một file JAR được nhìn thấy |
| Runtime đã cập nhật | `runtime/release`, vendor build id và advisory | Chỉ `java -version` trên build host |
| App vẫn chạy | Smoke test launcher trong app image | Chỉ thấy `javac` PASS |
| Installer chứa image mới | Kiểm tra package payload/version/provenance | Chỉ tạo installer thành công |
| Phiên bản/nhận dạng upgrade | `--app-version`, package name, UUID/identifier tùy OS | Chỉ đổi tên file installer |
| Ký và integrity | Kiểm tra chữ ký, SHA-256, SBOM, attestation | Chỉ hash source code |
| Nâng cấp không mất dữ liệu | Test từ bản production trước đó có config/database mẫu | Chỉ fresh install |
| Rollback khả thi | Thử quay lại bản trước với dữ liệu và migration phù hợp | Chỉ giữ installer cũ |

### Kiểm tra SHA-256 trước và sau package

PowerShell Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 .\stage-patched\library.jar
Get-FileHash -Algorithm SHA256 .\dist\PatchDemo\app\library.jar
~~~

Đường dẫn image trên là **layout Windows điển hình**, cần kiểm tra thực tế. Nếu JAR được copy nguyên vẹn, hash staged và hash trong image phải khớp. Nếu pipeline thay đổi artifact sau build, phải xác minh theo quy trình biến đổi đó, không suy từ tên file.

**SBOM (Software Bill of Materials)** nên liệt kê những thành phần đi kèm, gồm thư viện Java trực tiếp/transitive và thông tin runtime. Để kiểm tra một CVE, phải đối chiếu advisory và quét **gói cuối**, không dùng hash khác nhau như bằng chứng duy nhất.

### Dấu vết release tối thiểu

Lưu metadata:

- Source revision/commit và CI build ID.
- Version ứng dụng/package.
- JDK vendor/version/build và OS/architecture dùng tạo runtime.
- Dependency lockfile và SBOM có version thật.
- SHA-256 của image/installer đã phát hành.
- Kết quả unit/integration/smoke/upgrade tests.
- Trạng thái ký số/notarization nếu áp dụng.
- Advisory hoặc issue đã được xử lý, release notes và cách rollback.

**Không đòi mọi build từ cùng source phải có hash giống nhau** khi chưa làm reproducible build: timestamps và metadata trong JAR/installer có thể khác. Nhưng cần bảo đảm **một artifact đã chọn phát hành** có hash xác định để đối chiếu ở từng điểm phân phối.

## 9. Thử nâng cấp và rollback trước khi rollout

Một app image chạy tốt chưa chứng minh bản cài đặt cũ có thể được nâng cấp an toàn. Test nên bao gồm:

1. **Cài mới:** installer mới trên hệ điều hành sạch.
2. **Nâng cấp:** cài một version production cũ thật sự, thêm dữ liệu mẫu rồi cài version mới.
3. **Giữ nguyên dữ liệu người dùng:** cấu hình, database và cache có giá trị không bị vô tình xóa.
4. **Launcher/shortcut/service:** sau upgrade trỏ đúng ứng dụng và runtime mới.
5. **Không còn thư viện cũ:** xác nhận không có JAR dễ tổn thương trong payload được nạp.
6. **Runtime thật:** đọc file metadata trong bản đã cài, không chỉ trong build artifact.
7. **Đường lỗi:** disk đầy, thiếu quyền, chương trình đang chạy, package rollback thất bại.
8. **Migration:** nếu có thay đổi schema, ghi rõ khả năng đọc dữ liệu của bản trước.
9. **Giám sát rollout:** tỷ lệ thiết bị đã nhận bản mới, crash/startup errors, kênh hỗ trợ.

**Không mặc định downgrade luôn an toàn.** Nhiều installer có quy tắc không cho hạ version, và dữ liệu đã migrate lên schema mới có thể không tương thích với app cũ. Kế hoạch rollback phải bao gồm **cả code và dữ liệu**, đồng thời giữ artifact cũ đã được xác minh.

**Vị trí lưu dữ liệu:** không nên lưu dữ liệu người dùng cần bảo toàn trong folder `app`/`runtime` có thể bị installer thay thế. Dùng đường dẫn dữ liệu ứng dụng theo quy ước của OS/user profile hoặc database bên ngoài, có backup/migration phù hợp.

## 10. Những lỗi thường gặp và cách sửa

| Sai lầm | Rủi ro | Biện pháp |
|---|---|---|
| Cập nhật dependency ở source nhưng phát hành installer cũ | Máy khách vẫn dùng bản lỗi | Rebuild staging, image, installer |
| Dùng staging còn JAR cũ | Classpath có thể nạp bản chưa vá | Staging sạch và kiểm tra runtime payload |
| Dùng lại fat JAR có dependency dễ tổn thương | Vẫn chứa code cũ dù có JAR mới bên ngoài | Rebuild fat JAR, quét artifact cuối |
| Đổi JDK trên máy build nhưng reuse `--runtime-image` cũ | Java runtime đóng kèm vẫn chưa sửa | Tạo lại custom runtime bằng patched JDK |
| Dựa vào `javac --release 17` để xác định runtime version | Lẫn target bytecode với runtime | Đọc metadata runtime trong image |
| Sửa mỗi file `runtime/release` | Không thay byte Java runtime | Rebuild bằng JDK đã sửa |
| Dùng `--app-image` cùng `--runtime-image` trong một bước tạo installer | Lựa chọn xung đột | Thay runtime trước khi tạo image |
| Chỉ tăng `--app-version` | Metadata mới nhưng payload có thể cũ | Kiểm tra JAR/runtime hash và launcher |
| Không tăng package version | Nâng cấp không nhận version mới | Versioning hợp lệ và kiểm thử install |
| Thay Windows Upgrade UUID mỗi lần | Gói có thể bị coi là sản phẩm khác | Dùng UUID ổn định và test upgrade |
| Tin `--win-update-url` tự update phần mềm | Máy khách không tự nhận bản vá | Xây kênh update thực tế |
| Tạo installer từ image trước khi patch | Installer vẫn mang runtime/lib cũ | Kiểm tra đường dẫn/provenance image |
| Chỉ test trong IDE | Không phát hiện lỗi launcher/classpath/module | Chạy image đã đóng gói |
| Không ký lại sau sửa file trong app image | Chữ ký có thể không còn hợp lệ | Ký hoàn chỉnh artifact sau rebuild |
| Phát hành image Windows sang Linux/macOS | Native launcher không tương thích | Package riêng theo OS/architecture |
| Bỏ kiểm tra ABI sau dependency update | `NoSuchMethodError`, lỗi runtime | Recompile/test và kiểm tra compatibility |
| Ghi database vào installation folder | Dễ mất dữ liệu khi upgrade | Tách user data và thiết kế migration |
| Không giữ rollback artifact | Khó phục hồi khi regression | Lưu bản trước, backup và quy trình phục hồi |
| Xem hash khác là bằng chứng vá CVE | Kết luận không được hỗ trợ | Advisory + version/build + scan SBOM |
| Dùng JDK không được hỗ trợ | Không có bản vá mới | Chọn nhánh/vendor có support theo policy |

## 11. Quy trình CI/CD khuyến nghị

~~~text
Security advisory / Bug fix
             |
             v
Resolve patched dependency / JDK
             |
             v
Update lockfiles, dependency tree, SBOM
             |
             v
Build / Unit / Integration tests
             |
             v
Fresh staging with runtime dependencies
             |
             v
jpackage --type app-image
             |
             v
Verify embedded JARs and runtime/release
             |
             v
Run native launcher smoke tests
             |
             v
Build native installer for target OS
             |
             v
Upgrade tests and user data checks
             |
             v
Signing / notarization / SHA-256
             |
             v
Release notes, rollout, monitoring
             |
             v
Rollback if needed
~~~

### Tối thiểu cần chốt trong CI

- **JDK toolchain cố định** theo bản build được chọn, tránh thay đổi ngẫu nhiên giữa các lần chạy.
- **Dependency version cố định/kiểm kê**, không âm thầm kéo thay đổi không được review.
- **Staging mới mỗi release**, không mang file từ build trước.
- **Artifact verification** ở đúng output image/installer.
- **OS-specific runners** tương ứng target Windows/Linux/macOS.
- **Ký sau khi đã hoàn thiện artifact**, tránh sửa nội dung sau ký.
- **Cơ chế rollout và rollback**, không dừng ở `jpackage exit 0`.

Lưu ý khi đổi JDK mới: không chỉ quan sát mỗi compile PASS; các thay đổi runtime/module graph có thể ảnh hưởng `ServiceLoader`, TLS, JNI, locale hoặc native dependencies. Smoke test bằng launcher thật và thử chức năng quan trọng.

## 12. Checklist release bản vá

- [ ] Đã xác định rõ phiên bản thư viện/JDK lỗi và bản đã sửa qua advisory.
- [ ] Mọi dependency trực tiếp, transitive, shaded/nested đã được kiểm tra.
- [ ] Build và staging sạch, không có JAR lỗi còn sót.
- [ ] Runtime đã được build từ JDK đã cập nhật hoặc custom runtime mới.
- [ ] `runtime/release` trong image đúng vendor/build cần phát hành.
- [ ] Image còn đủ module/provider/native capabilities của ứng dụng.
- [ ] App JAR, library JAR và resource đúng đường dẫn/classpath.
- [ ] `--app-version` của package mới hợp lệ.
- [ ] Windows Upgrade UUID/Linux package identity/macOS identifier phù hợp nếu có upgrade.
- [ ] Đã tạo lại app image và test native launcher.
- [ ] Installer được tạo **từ image mới**, không phải bản cũ.
- [ ] Có SBOM và SHA-256/provenance của artifact cuối.
- [ ] Installer được ký và notarized nếu yêu cầu.
- [ ] Cài mới, nâng cấp từ bản trước, bảo toàn dữ liệu được kiểm thử.
- [ ] Có rollback artifact và kế hoạch database/config migration.
- [ ] Có release notes và giám sát tỷ lệ cài đặt bản vá.

## 13. Tự kiểm tra

**Câu 1.** Đã cập nhật JDK trên Windows người dùng, nhưng ứng dụng chạy bằng app image chứa runtime. Runtime bên trong có tự được vá không?

**Đáp án:** Không. Self-contained launcher thường dùng runtime đi kèm. Cần rebuild runtime/app image/installer mới bằng JDK đã vá và phân phối đến máy khách.

**Câu 2.** `--app-version 1.0.1` có nghĩa Java runtime là Java 1.0.1 không?

**Đáp án:** Không. Đó là version ứng dụng/package. Dependency version và bundled Java runtime version là hai thông tin khác cần kiểm chứng riêng.

**Câu 3.** `javac --release 17` có ép `jpackage` dùng Java 17 runtime không?

**Đáp án:** Không. `--release` chọn target bytecode/API, còn runtime được lấy theo JDK dùng packaging hoặc `--runtime-image`.

**Câu 4.** Vì sao phải tạo staging mới sau khi thay dependency?

**Đáp án:** Tránh JAR cũ còn tồn tại cạnh JAR đã vá, được đóng nhầm vào image hoặc được classpath nạp không mong muốn.

**Câu 5.** Muốn thay Java runtime trong installer xây từ app image sẵn, có thể dùng đồng thời `--app-image old-image --runtime-image new-runtime` không?

**Đáp án:** Không. Tạo **app image mới** chứa runtime mới trước, rồi build installer từ image ấy.

**Câu 6.** Trong ví dụ, app JAR không đổi nhưng launcher v2 hiển thị `library=1.0.1`. Vì sao?

**Đáp án:** Library API giữ nguyên, nhưng thư viện trong `stage2/library.jar` có implementation mới. Image v2 mang byte library mới. Với thư viện thật thay API/ABI, phải build/test lại app.

**Câu 7.** Hash mới khác hash cũ có chứng minh một CVE đã vá không?

**Đáp án:** Không. Chỉ chứng minh dữ liệu binary khác. Phải xác minh bản đã sửa theo advisory và kiểm tra artifact cuối.

**Câu 8.** Tại sao không nên đổi `--win-upgrade-uuid` ở mỗi Windows release?

**Đáp án:** UUID ổn định giúp hệ thống nhận các package là cùng dòng nâng cấp. Đổi tùy tiện có thể khiến installer không nhận bản mới là bản thay thế; phải test nâng cấp thật.

**Câu 9.** Tại sao dữ liệu người dùng không nên nằm trong thư mục app image?

**Đáp án:** Installer có thể thay thế thư mục cài đặt khi upgrade. User data cần nơi lưu riêng và chính sách backup/migration.

**Câu 10.** Cập nhật JDK minor/patch rồi chỉ chạy unit tests có đủ không?

**Đáp án:** Chưa đủ. Cần kiểm tra runtime image thật, service/module providers, launcher và test upgrade/installation theo nền tảng.

**Câu 11.** Nếu app image được tạo bằng JDK đã vá nhưng installer lại lấy `--app-image` trỏ tới image cũ, bản phát hành có được vá không?

**Đáp án:** Không thể kết luận vậy. Installer có thể vẫn chứa runtime/JAR cũ; pipeline phải kiểm tra provenance và payload đầu ra.

**Câu 12.** Vì sao cần test rollback khi release chỉ nhằm bản vá security?

**Đáp án:** Bản vá vẫn có thể gây regression hoặc migration không tương thích. Rollback phải xét cả installer behavior lẫn dữ liệu đã thay đổi.

## 14. Tài liệu tham khảo chính thức

- [Oracle Java SE 25 — jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): `--app-version`, `--runtime-image`, `--app-image`, `--win-upgrade-uuid`, `--linux-app-release`.
- [Oracle Java SE 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): Java runtime trong app image và thay đổi service binding từ JDK 25.
- [Oracle Java SE 25 — Image and Runtime Modifications](https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html): tạo runtime bằng `jlink`, build installer từ app image và cặp option xung đột.
- [Oracle Java SE 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): version app, output OS-specific và runtime đi kèm.
- [Oracle Java SE 25 — Manage the Installation](https://docs.oracle.com/en/java/javase/25/jpackage/manage-installation.html): lựa chọn cài đặt và các tùy chọn installer.
- [Oracle Java SE 26 — Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/26/jpackage/index.html): tài liệu tham khảo cho công cụ trên JDK mới hơn.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` chính thức từ JDK 16.
- [Oracle Java SE 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): cách tạo runtime image với module list.

**Ghi nhớ:** **Chỉ khi dependency hoặc Java runtime đã được thay trong application image và installer mới thực sự đến máy người dùng, bản vá mới được phân phối.** Dùng staging sạch, JDK được hỗ trợ và đã cập nhật, verify JAR/runtime bên trong image, quản lý version/identity nâng cấp, ký và kiểm thử cài mới, nâng cấp, rollback trước khi phát hành.