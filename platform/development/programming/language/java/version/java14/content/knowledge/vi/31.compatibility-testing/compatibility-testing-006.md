# Kiểm thử phần đóng gói cùng nền tảng đích — Java jpackage

## 1. Bài toán và kết quả cần đạt

Một chương trình Java có thể vượt qua tất cả unit tests và chạy tốt với `java -jar app.jar` nhưng **không chạy được sau khi đóng gói thành phần mềm cài đặt**. Lý do nằm ở sự khác nhau giữa Java code và **artifact giao cho người dùng**:

- Native launcher không tìm được class chính, JAR, resources hoặc Java runtime.
- App-image được tạo với Java runtime thiếu module, provider hoặc thư viện native cần thiết.
- Bản build được tạo trên một hệ điều hành/kiến trúc CPU không tương thích với máy người dùng.
- Installer có vấn đề về dependencies, chữ ký, quyền, shortcut, file associations, services, upgrade hoặc uninstall.
- Chương trình vô tình dựa vào JDK, biến môi trường, working directory và files chỉ có trên máy lập trình viên.
- Bản đóng gói được tạo đúng nhưng người dùng không có quyền ghi cấu hình/log tại thư mục cài đặt.

**Mục tiêu:** thiết kế kiểm thử đúng **nền tảng đích** với bốn tầng: kiểm thử Java artifact, kiểm thử `jpackage --type app-image`, kiểm thử native installer và kiểm thử vòng đời sau cài đặt. Người học sẽ tự tạo một app-image Windows thật với JAR, resource và bundled runtime; chạy được native launcher bằng các arguments khác nhau và cả sau khi di chuyển image.

**Lưu ý về Java 14:** `jpackage` lần đầu được giới thiệu ở JDK 14 dưới dạng incubating tool nhưng **trở thành production-ready từ JDK 16 (JEP 392)**. Bài chỉ hướng dẫn công cụ `jpackage` chính thức đang áp dụng, không sử dụng module `jdk.incubator.jpackage` hoặc flags legacy. Java sample dùng `javac --release 17` và được chạy kiểm chứng trên Windows với OpenJDK 24.0.2. Những ví dụ MSI/DMG/PKG/DEB/RPM là **hướng dẫn thử trên OS thích hợp**, không tuyên bố đã thực thi các installer ấy.

## 2. Quy tắc bắt buộc: native package phải build trên hệ điều hành đích

Theo tài liệu **Oracle Java SE 26 — Packaging Overview**:

> Application packages must be built on the target platform.

Nghĩa là muốn tạo một native installer để chạy trên **Windows** thì thực thi `jpackage` trên Windows; muốn tạo **DMG/PKG** thì chạy trên macOS; muốn tạo **DEB/RPM** thì chạy trên Linux phù hợp. Công cụ **không hỗ trợ cross-platform native packaging trực tiếp**.

| Host OS chạy `jpackage` | Kiểu artifact hỗ trợ | Công cụ bản địa cần lưu ý | Môi trường phải test |
| --- | --- | --- | --- |
| Windows | `app-image`, `msi`, `exe` | WiX khi tạo MSI/EXE installer | Windows tương thích và CPU architecture thực tế |
| macOS | `app-image` (.app), `dmg`, `pkg` | Xcode command-line tools với một số thao tác ký/tùy chỉnh DMG; signing identities nếu cần | macOS phù hợp, Gatekeeper/signing/notarization |
| Linux | `app-image`, `deb`, `rpm` | Công cụ build package như `fakeroot` (Ubuntu) hoặc `rpm-build` (Red Hat) | Các distro/versions/architectures sản phẩm hỗ trợ |

Đây là **dạng file do jpackage hỗ trợ**; không phải cam kết một Windows x64 build sẽ chạy trên Windows ARM64, hay một DEB chạy trên mọi bản Linux. Còn phải xét **architecture, thư viện native, OS release, quy định ký/installation**.

**Một source Java** có thể build trên nhiều OS; **nhiều package native** phải được tạo/test riêng. Nếu cần hai định dạng Windows `msi` và `exe`, chạy `jpackage` cho từng format.

## 3. Cần kiểm thử những cấp độ nào?

```text
Java code / dependencies
        |
        v
1. Source + API + bytecode tests
   javac --release N, unit tests, dependency audit
        |
        v
2. App-image build trên target OS
   jpackage --type app-image
        |
        v
3. Native launcher + bundled runtime smoke tests
   resources, JVM options, args, OS libs, logs, permissions
        |
        v
4. Native installer tests trên môi trường thử cô lập
   install, shortcuts, signing, upgrade, uninstall
        |
        v
Release candidate chỉ khi mọi gate cần thiết đều PASS
```

| Câu hỏi | Kiểm thử thích hợp | Không được suy ra |
| --- | --- | --- |
| Source có dùng cú pháp/API mới hơn mức cam kết? | `javac --release N` | Không kiểm tra mọi dependency/runtime behavior |
| JAR có class chính/resources? | `jar --list`, dependency inspection | Không chứng minh launcher/package hoạt động |
| Runtime image đủ module? | `jpackage --type app-image` và chạy use cases | Không suy ra chỉ từ JDK developer |
| Native executable chạy đúng? | Chạy launcher trong image | Không đủ cho installer install/uninstall |
| MSI/PKG/DEB cài được? | Cài artifact thật trên VM/test host | Không suy ra từ app-image PASS |
| Chữ ký/notarization hợp lệ? | Kiểm tra final artifact bằng cơ chế OS | Không suy ra từ app khởi chạy ở IDE |
| Nâng cấp/gỡ đúng? | Test bản N rồi N+1 và uninstall | Không suy ra từ cài mới |
| Không cần Java ngoài máy? | Test self-contained package trên máy sạch | Không suy ra từ `java -jar` trên máy build |

**Quan trọng:** nếu chỉ kiểm chứng `--type app-image` thì kết quả cuối phải gọi đúng là **app-image smoke PASS**, không gọi là **MSI/macOS/Linux installer PASS**.

## 4. Ma trận tương thích cần định nghĩa trước khi phát hành

Một bản Java desktop có nhiều trục độc lập:

1. **OS**: Windows 10/11, phiên bản macOS, Ubuntu/RHEL/Debian hoặc bản OS sản phẩm thực sự cam kết.
2. **CPU**: `x86_64/amd64`, `aarch64/arm64` hoặc kiến trúc khác có JDK/native libraries tương ứng.
3. **JDK vendor/version khi build**: compiler và packager thực tế dùng.
4. **Bundled Java runtime**: từ `jlink` hay `--runtime-image`, modules và version.
5. **Java compatibility baseline**: `--release N` cho source và dependencies.
6. **Dạng phân phối**: Windows MSI/EXE, Mac DMG/PKG, Linux DEB/RPM.
7. **Quyền cài và chạy**: per-user/per-machine, service account, user thường và UAC/policy.
8. **Đường dẫn**: có khoảng trắng/Unicode, install directory chỉ đọc, working directory khác IDE.
9. **Tính năng tích hợp**: shortcut, file associations, tray/menu, app services, alternative launchers.
10. **Vòng đời**: clean install, upgrade, repair/reinstall, uninstall, giữ hoặc migrate user data.

Gợi ý phân tầng CI:

| Gate | Tần suất | Kỳ vọng |
| --- | --- | --- |
| Compile/unit tests | Mỗi commit | Bytecode/API hợp lệ theo `--release N` |
| App-image smoke | Mỗi build có packaging | Native launcher + resources + runtime hoạt động |
| Native installer smoke | Mỗi release candidate | Install/start/uninstall trên VM sạch |
| Full OS/arch/distro matrix | Nightly hoặc trước release | Mọi platform được cam kết đều có bằng chứng |
| Security/signing/distribution | Trước khi phát hành artifact cuối | Publisher, signature/trust, policy đạt yêu cầu |

Không bắt buộc thử mọi tổ hợp không liên quan; chỉ **đánh dấu PASS cho platform đã thực sự được thử**.

## 5. Runtime kèm theo và giới hạn của `--release`

Ứng dụng Java có thể được biên dịch bằng:

```bash
javac --release 17 ...
```

Điều này kiểm soát **ngôn ngữ, JDK API và class-file target Java 17** theo compiler. Nó **không** quyết định OS hoặc Java runtime mà `jpackage` sẽ đóng kèm.

- Khi không đưa `--runtime-image`, `jpackage` thường gọi `jlink` để tạo một Java runtime image từ JDK dùng để package.
- Khi đưa `--runtime-image <dir>`, công cụ đóng gói runtime đã được tạo sẵn; phải bảo đảm nó đúng OS/arch, modules và version.
- Với **named modules**, runtime phải chứa main module và dependencies cần thiết.
- Với **classpath/non-modular JAR**, runtime mặc định được tạo theo cấu hình classpath apps, nhưng vẫn cần smoke tests cho những thành phần tải động.

Nếu dùng JDK 24 để package một chương trình `--release 17`, bundled runtime thường là runtime do **JDK 24** tạo, **không tự thành JDK 17**.

**Lỗi thường gặp:** ứng dụng chạy `java -jar` trên JDK developer chứa rất nhiều modules; khi đưa vào custom runtime thiếu module, native launcher thất bại. Hãy test **launcher trong app-image**, thay vì chỉ test JAR bằng một JDK ngoài.

### 5.1. Chỉ số và bằng chứng đúng

- `java -version` trên host cho biết **host Java** trong PATH; không đảm bảo bundled runtime cùng version.
- `System.getProperty("java.home")` trong app qua **native launcher** cho biết Java runtime đang chạy.
- `runtime/release` và cấu trúc thư mục trong image giúp xác minh runtime được tạo.
- `jdeps` giúp phân tích module dependencies; không phát hiện hoàn toàn reflection, `ServiceLoader`, JNI hoặc tải class động.
- `jlink` được dùng khi cần tự tạo runtime image; giữ chính xác modules/providers sản phẩm cần.

### 5.2. Thay đổi thực tế từ JDK 25+: service bindings

Tài liệu Oracle Java SE 26 nêu rõ: **từ JDK 25, runtime image do `jpackage` tạo mặc định không còn tự bao gồm service bindings như trước**. Ứng dụng phụ thuộc provider discovery có thể gặp khác biệt sau khi nâng JDK packager.

Khi cần binding provider modules, đánh giá lựa chọn `jlink --bind-services` qua `--jlink-options`:

```bash
jpackage --type app-image --name ProviderApp \
  --input input --main-jar app.jar \
  --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services"
```

Lệnh trên là **minh họa**, chưa chạy trong test Windows ở bài. Nếu tự chỉ định `--jlink-options`, phải cân nhắc các default options của công cụ. Bật `--bind-services` có thể đưa thêm provider modules vào runtime và làm tăng kích thước image.

**Không tự kết luận mọi ứng dụng đều phải bật `--bind-services`**: chỉ làm vậy khi code dùng provider discovery phù hợp và smoke tests xác nhận nhu cầu thực tế.

## 6. Ví dụ Windows hoàn chỉnh: kiểm thử app-image và native launcher

Chương trình sẽ kiểm tra:

- Resource thực sự nằm trong JAR.
- JVM option `-Ddemo.channel=stable` được launcher áp dụng.
- Default argument và argument có dấu cách.
- Windows OS trong lượt thử.
- Runtime `java.home` nằm dưới image tên `Target Platform Demo`.
- Application log được tạo trong thư mục riêng, không phụ thuộc nơi cài đặt.
- Toàn bộ image có thể di chuyển và chạy từ working directory khác.

### 6.1. Cấu trúc thử nghiệm

```text
package-smoke/
├── source code/
│   └── demo/
│       └── TargetPackageSmoke.java
├── resource files/
│   └── demo/
│       └── banner.txt
├── compiled classes/
├── input jars/
│   └── app.jar
├── output images/
├── build scratch/
├── user data logs/
└── another cwd/
```

Nội dung **`resource files/demo/banner.txt`**:

```text
packaged-ok
```

### 6.2. File `TargetPackageSmoke.java`

Lưu toàn bộ code sau tại `source code/demo/TargetPackageSmoke.java`:

```java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.Locale;

public final class TargetPackageSmoke {
    public static void main(String[] args) throws Exception {
        String resource;
        try (InputStream in = TargetPackageSmoke.class
                .getResourceAsStream("/demo/banner.txt")) {
            if (in == null) {
                throw new IllegalStateException("missing resource");
            }
            resource = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }

        String dataRoot = System.getenv("TARGET_SMOKE_LOG_DIR");
        if (dataRoot == null || dataRoot.isBlank()) {
            throw new IllegalStateException(
                    "TARGET_SMOKE_LOG_DIR is required");
        }

        Path log = Path.of(dataRoot).resolve("smoke-result.txt");
        Files.createDirectories(log.getParent());
        Files.writeString(
                log,
                String.join("|", args) + System.lineSeparator(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND);

        System.out.println("resource=" + resource);
        System.out.println("channel="
                + System.getProperty("demo.channel", "missing"));
        System.out.println("args=" + Arrays.toString(args));
        System.out.println("osWindows="
                + System.getProperty("os.name")
                    .toLowerCase(Locale.ROOT).contains("windows"));
        System.out.println("embeddedRuntime="
                + Path.of(System.getProperty("java.home"))
                    .toString().contains("Target Platform Demo"));
        System.out.println("logCreated="
                + Files.isRegularFile(log));
    }
}
```

**Giải thích:**

- `getResourceAsStream` kiểm tra resource đã được đóng gói vào JAR, không đọc file bên ngoài project.
- `System.getProperty("demo.channel")` cho phép xác minh launcher đã nhận `--java-options`.
- `Arrays.toString(args)` cho thấy khi truyền `"North Region"`, Java nhận **một** argument.
- `System.getProperty("java.home")` cho thấy JVM sử dụng khi chạy. Biểu thức `contains("Target Platform Demo")` chỉ là check đơn giản **phục vụ bản image Windows với tên đã chọn**, không phải phép kiểm chứng runtime di động cho mọi app.
- `TARGET_SMOKE_LOG_DIR` là directory do test cung cấp, đảm bảo app không cố ghi vào `Program Files` hoặc thư mục image.
- Code demo viết arguments ra log để test. Không log password, token hoặc PII trong ứng dụng thật.

### 6.3. Dùng PowerShell tạo workspace, biên dịch và đóng JAR

Chạy trên Windows với JDK 17+ phù hợp:

```powershell
$root = Join-Path $env:TEMP (
    "package smoke " + [guid]::NewGuid().ToString("N")
)

$source = Join-Path $root "source code\demo"
$resourceDir = Join-Path $root "resource files\demo"
$classes = Join-Path $root "compiled classes"
$input = Join-Path $root "input jars"
$dest = Join-Path $root "output images"
$scratch = Join-Path $root "build scratch"
$logDir = Join-Path $root "user data logs"
$otherCwd = Join-Path $root "another cwd"

foreach ($p in @($source,$resourceDir,$classes,$input,
                 $dest,$scratch,$logDir,$otherCwd)) {
    New-Item -ItemType Directory -Path $p -Force | Out-Null
}

# Lưu Java source ở mục 6.2 và banner.txt ở mục 6.1 trước.
$javaFile = Join-Path $source "TargetPackageSmoke.java"

javac --release 17 -d $classes $javaFile
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

$jarFile = Join-Path $input "app.jar"

$resourceRoot = Join-Path $root "resource files"
jar --create --file $jarFile -C $classes . -C $resourceRoot demo/banner.txt
if ($LASTEXITCODE -ne 0) { throw "jar failed" }

jar --list --file $jarFile
```

Danh sách trong JAR phải chứa:

```text
demo/TargetPackageSmoke.class
demo/banner.txt
```

Lưu ý `jar --create` ở đây có `-C` để thay working directory lúc lấy files, giúp giữ **đúng entry names trong JAR**. Nếu resource chưa được đưa vào JAR, chương trình sẽ báo `missing resource` dù nó chạy tốt từ IDE trước đó.

### 6.4. Dùng `jpackage` tạo app-image Windows

```powershell
$options = @(
    "--type", "app-image",
    "--name", "Target Platform Demo",
    "--input", $input,
    "--dest", $dest,
    "--temp", $scratch,
    "--main-jar", "app.jar",
    "--main-class", "demo.TargetPackageSmoke",
    "--arguments", "from-package",
    "--java-options", "-Ddemo.channel=stable",
    "--win-console",
    "--verbose"
)

$buildLog = Join-Path $root "jpackage verbose build.log"
& jpackage @options 2>&1 |
    Out-File -LiteralPath $buildLog -Encoding utf8

if ($LASTEXITCODE -ne 0) {
    throw "jpackage failed; inspect build log"
}
```

`@options` là PowerShell **array splatting**; mỗi path có dấu cách được truyền như một argument. Không tự ghép command có user input rồi gọi `Invoke-Expression`.

Option quan trọng:

| Option | Ý nghĩa |
| --- | --- |
| `--type app-image` | Chỉ tạo folder runnable; **không cài installer** |
| `--name` | Tên app/image/launcher |
| `--input` | Thư mục chứa JAR/resources |
| `--main-jar` | Tên JAR **tương đối với `--input`** |
| `--main-class` | Java entry point |
| `--arguments` | Arguments mặc định nếu user không truyền gì |
| `--java-options` | JVM options truyền bởi launcher |
| `--win-console` | Console launcher Windows, tiện quan sát stdout/stderr |
| `--verbose` | Log build chi tiết |
| `--temp` | Thư mục staging mới/rỗng; được giữ lại để debug |

Lệnh này **không yêu cầu tạo MSI installer** và không thay đổi cài đặt hệ thống. `--temp` được chỉ định phải **mới hoặc rỗng**; không dùng lại thư mục build chứa dữ liệu quan trọng.

### 6.5. Kiểm tra file payload và bundled runtime

```powershell
$image = Join-Path $dest "Target Platform Demo"
$launcher = Join-Path $image "Target Platform Demo.exe"
$packedJar = Join-Path $image "app\app.jar"
$packedConfig = Join-Path $image "app\Target Platform Demo.cfg"
$runtimeMeta = Join-Path $image "runtime\release"

Test-Path -LiteralPath $launcher
Test-Path -LiteralPath $packedJar
Test-Path -LiteralPath $packedConfig
Test-Path -LiteralPath $runtimeMeta
```

**Kết quả đã chạy trên Windows/OpenJDK 24.0.2:**

```text
True
True
True
True
```

Đây là layout của **Windows app-image** trong bài; Linux/macOS có cấu trúc khác, không copy path Windows sang hệ khác.

Kiểm tra bytes JAR có được sao chép nguyên:

```powershell
$hashIn = (Get-FileHash -LiteralPath $jarFile -Algorithm SHA256).Hash
$hashPacked = (Get-FileHash -LiteralPath $packedJar -Algorithm SHA256).Hash

Write-Output ("payloadSha256Match=" + ($hashIn -eq $hashPacked))
```

**Output thực tế:**

```text
payloadSha256Match=True
```

Phép kiểm chứng này chỉ xác minh **một JAR được copy vào image**; nó không chứng minh gói native đã được ký hay mọi runtime resources đều hợp lệ.

### 6.6. Chạy launcher thay vì chạy JAR với Java ngoài

```powershell
$env:TARGET_SMOKE_LOG_DIR = $logDir

Push-Location $otherCwd
try {
    & $launcher
    Write-Output ("exit=" + $LASTEXITCODE)

    & $launcher "North Region"
    Write-Output ("exit=" + $LASTEXITCODE)
}
finally {
    Pop-Location
}
```

**Output lần đầu — không truyền CLI arguments:**

```text
resource=packaged-ok
channel=stable
args=[from-package]
osWindows=true
embeddedRuntime=true
logCreated=true
exit=0
```

**Output lần sau — một argument có dấu cách:**

```text
resource=packaged-ok
channel=stable
args=[North Region]
osWindows=true
embeddedRuntime=true
logCreated=true
exit=0
```

`--arguments from-package` được dùng khi không có args từ user; khi user truyền `"North Region"`, nó **thay thế** default args. Ba dấu hiệu quan trọng là `resource=packaged-ok`, `channel=stable` và `embeddedRuntime=true` trong lượt test đã thực hiện.

Xác minh file log:

```powershell
Get-Content -LiteralPath (Join-Path $logDir "smoke-result.txt")
```

Nội dung sau hai lần chạy:

```text
from-package
North Region
```

Chạy từ `$otherCwd` giúp kiểm tra code không phụ thuộc vào current working directory của IDE hoặc của thư mục chứa launcher.

## 7. Kiểm thử di chuyển toàn bộ app-image

Một ứng dụng có thể chạy trong workspace build vì vẫn tham chiếu path của developer. Test đơn giản là **chuyển toàn bộ image sang directory khác** và chạy lại:

```powershell
$movedParent = Join-Path $root "moved full image"
New-Item -ItemType Directory -Path $movedParent -Force | Out-Null

$movedImage = Join-Path $movedParent "Target Platform Demo"
Move-Item -LiteralPath $image -Destination $movedImage

$movedLauncher = Join-Path $movedImage "Target Platform Demo.exe"

Push-Location $otherCwd
try {
    & $movedLauncher "moved-image"
    Write-Output ("exit=" + $LASTEXITCODE)
}
finally {
    Pop-Location
}
```

**Output đã xác minh:**

```text
resource=packaged-ok
channel=stable
args=[moved-image]
osWindows=true
embeddedRuntime=true
logCreated=true
exit=0
```

File log cuối cùng:

```text
from-package
North Region
moved-image
```

Đây là bằng chứng image trong **môi trường thử Windows này** không bị phụ thuộc vào location của workspace gốc. Không copy riêng `.exe` — launcher còn cần JAR/config/runtime của **toàn bộ image**.

**Giới hạn:** test chuyển folder **không** xác nhận cài đặt MSI, shortcut, update/uninstall hoặc signature. Đó là tầng kiểm thử riêng.

## 8. Kiểm thử Windows MSI/EXE trên nền tảng đích

Khi app-image đạt smoke test, trên **Windows runner** được chuẩn bị WiX phù hợp có thể tạo một installer:

```powershell
$nativeOptions = @(
    "--type", "msi",
    "--name", "Target Platform Demo",
    "--input", "C:\Package Workspace\input jars",
    "--main-jar", "app.jar",
    "--main-class", "demo.TargetPackageSmoke",
    "--dest", "C:\Package Workspace\installers"
)

jpackage @nativeOptions
```

Đây là **lệnh minh họa**: đường dẫn phải được thay bằng artifact thực tế; không phải lệnh đã chạy trên Windows máy test ở bài (bài chỉ tạo app-image). Tạo installer thực yêu cầu toolchain native được hỗ trợ.

### 8.1. Các điểm test của installer Windows

- Artifact có đúng version, name, publisher, architecture, metadata?
- Windows Installer/EXE cài được từ môi trường **sạch**, không cần JDK toàn cục?
- Scope per-user/per-machine và quyền nâng cao được yêu cầu **đúng** theo policy?
- Startup/Start Menu/Desktop shortcuts có hoạt động và dùng bundled runtime?
- User thường mở được ứng dụng, ghi log vào `%LOCALAPPDATA%` hoặc vùng phù hợp, **không ghi vào `Program Files`**?
- File associations, additional launchers, service registration nếu dùng có đúng?
- Install version N rồi upgrade N+1 có giữ/migrate user data theo hợp đồng?
- Uninstall có gỡ đúng binary, shortcuts, registration và xử lý data theo chính sách?
- File package có được ký và verified trên hệ thống đích nếu policy yêu cầu?

### 8.2. Log MSI khi cài lỗi

Trong **Windows VM test đã được cấp phép cài phần mềm**, Windows Installer cho phép verbose logging:

```powershell
$msiFile = "C:\Package Workspace\installers\Target Platform Demo.msi"
$installLog = "C:\Install Logs\install.log"

New-Item -ItemType Directory -Path (Split-Path -Parent $installLog) -Force | Out-Null
& msiexec.exe /i $msiFile /L*v $installLog
```

Lệnh này **bắt đầu cài MSI nếu chạy**, nên không thực hiện tùy tiện trên máy dùng chung hoặc môi trường production. Tên MSI thực tế có thể có version/arch trong filename. `msiexec /L*v` chỉ áp dụng cho **MSI**, không phải mọi `.exe` wrapper và không có ý nghĩa khi chỉ tạo app-image.

Để kiểm tra signature Windows:

```powershell
Get-AuthenticodeSignature -FilePath $msiFile
```

Đọc publisher/chain/trust/policy thực tế; chỉ có file `.msi` hoặc một đối tượng signature chưa chứng minh gói đáng tin.

## 9. Kiểm thử macOS app/DMG/PKG trên chính Mac

Trên **macOS runner** với JDK phù hợp:

```bash
jpackage --type app-image --name TargetPlatformDemo \
  --input input --main-jar app.jar \
  --main-class demo.TargetPackageSmoke \
  --dest images
```

Sau khi app-image chạy đúng, có thể tạo `dmg` hay `pkg` bằng **hai lượt build riêng**:

```bash
jpackage --type dmg --name TargetPlatformDemo \
  --input input --main-jar app.jar \
  --main-class demo.TargetPackageSmoke \
  --dest installers
```

**Các lệnh này là minh họa, chưa chạy trong bài.** Cần thực hiện trên macOS thực, với resources/JAR đúng chuẩn bị trên runner đó.

Kiểm thử tối thiểu:

- App bundle `.app` chứa `Contents/Info.plist`, native launcher, resources và bundled runtime.
- Chạy từ Finder và terminal; GUI app có menu/Dock/permissions đúng.
- Đúng kiến trúc Intel/Apple Silicon và macOS versions mà sản phẩm cam kết.
- App/installer được ký bằng identity phù hợp nếu chính sách phân phối yêu cầu.
- Notarization và Gatekeeper được kiểm tra **trên artifact cuối cùng** như user tải/cài, không chỉ trên file source.
- Installer có thể cài, update và uninstall theo hệ thống macOS, không mất dữ liệu user ngoài chính sách.

Ví dụ kiểm tra **đối với app đã được ký**:

```bash
codesign --verify --verbose=2 "TargetPlatformDemo.app"
spctl --assess --verbose=2 --type execute "TargetPlatformDemo.app"
```

Hai lệnh trên phải chạy **trên macOS**, không phải Windows. **Được ký** không tự động đồng nghĩa **đã notarized**, và app chạy khi chưa được quarantine trên máy developer không chứng minh trải nghiệm Gatekeeper của user mới.

## 10. Kiểm thử Linux DEB/RPM trên đúng distro

Trên một **Linux runner** tương ứng:

```bash
jpackage --type deb --name target-platform-demo \
  --input input --main-jar app.jar \
  --main-class demo.TargetPackageSmoke \
  --dest installers
```

Dùng `--type rpm` khi tạo RPM trên hệ build phù hợp. `deb` và `rpm` là **hai hệ package khác nhau**, không thay thế việc kiểm thử trên distro mục tiêu.

Kiểm tra metadata trước khi cài:

```bash
dpkg-deb --info ./target-platform-demo*.deb
```

Với RPM:

```bash
rpm -qpi ./target-platform-demo*.rpm
```

Các file glob chỉ minh họa; phải dùng tên artifact thực tế. Thực hiện cài/gỡ **trong VM hoặc môi trường có quyền thử nghiệm**, rồi xác nhận:

- Package metadata và architecture.
- Native package-manager dependencies phù hợp distro/version.
- Executable permission, desktop entries, icons và file associations.
- Runtime/JAR/modules/native libraries đủ để chạy launcher thực tế.
- User thường ghi dữ liệu vào khu vực user được phép.
- Upgrade, reinstall và remove để package database sạch, dữ liệu giữ/xóa đúng policy.

Không kết luận một `.deb` chạy được trên Ubuntu thì tự chạy được trên mọi RHEL; khác toolchain, system libraries, package manager và các phiên bản.

## 11. Log, quyền và điều kiện máy sạch

### 11.1. Ba loại log là ba tầng

| Tầng lỗi | Log và công cụ |
| --- | --- |
| `jpackage` build lỗi | `--verbose`, `--temp` staging, compiler/package stdout/stderr |
| MSI/PKG/DEB/RPM install lỗi | Windows Installer `/L*v`, macOS Installer diagnostics hoặc Linux package-manager logs |
| App không khởi động | Native launcher console/OS events; application startup log |
| App khởi động rồi lỗi chức năng | Java stack trace, logging framework, telemetry theo chính sách |

`jpackage --verbose` **không** thu thập lỗi Java khi user mở ứng dụng nhiều ngày sau. Ngược lại application logger do Java tạo có thể **chưa tồn tại nếu launcher chết trước khi gọi main**.

### 11.2. Kiểm thử không phụ thuộc JDK developer

Một self-contained image đúng cần dùng **runtime kèm trong image**, không dựa vào `JAVA_HOME` hoặc `PATH` trỏ đến JDK của nhà phát triển. Hãy test trên máy sạch hoặc tài khoản/môi trường không có JDK riêng; đừng chỉ nhìn `java -version` của host để kết luận.

### 11.3. Quyền khi cài khác quyền khi chạy

Installer có thể cần quyền thay đổi thư mục chương trình; **ứng dụng runtime** lại thường chạy bằng user thông thường. Không ghi logs/config/cache vào `Program Files`, `/Applications` hoặc system paths được bảo vệ nếu không có hợp đồng quyền cụ thể.

Test negative:

- User thường không có quyền ghi directory cài đặt nhưng app vẫn chạy.
- Directory log/data cho user có quyền ghi, app tạo file/ghi lỗi đúng.
- Shortcut hoặc service khởi chạy từ working directory khác.
- Đường dẫn username/install có khoảng trắng/Unicode.
- Với service, test đúng service account thay vì account developer.

Không sửa ACL thư mục hệ thống thành writable cho mọi user để “qua test”.

## 12. Test ký, security và chuỗi cung ứng

Ngoài khả năng khởi động, artifact cuối cần qua gate bảo mật phù hợp:

- Tính checksum SHA-256 của file package để đối chiếu CI output và file phân phối.
- Windows: Authenticode publisher/trust chain trên executable/installer nếu policy yêu cầu.
- macOS: Code signature, entitlements, notarization/Gatekeeper trên artifact cuối.
- Linux: GPG/repo metadata, quyền script, dependency trust theo policy distro.
- Không nhét signing keys hoặc password vào stdout, Java args hay build logs.
- Ghi metadata JDK vendor/version, OS/arch, `jpackage` version/options, package version và checksum.
- Kiểm thử artifact **sau ký**; chữ ký hoặc repackaging có thể làm thay đổi bytes của file.
- Lập kế hoạch cập nhật **bundled runtime** khi JDK có security fixes: ứng dụng self-contained không tự dùng JDK mới chỉ vì host cài bản Java mới.

Đừng tắt Gatekeeper/antivirus hoặc luôn chạy dưới admin chỉ để làm một bản package chưa đúng policy trở thành “PASS”.

## 13. Upgrade, uninstall và dữ liệu người dùng

Một package có thể cài mới ổn nhưng lỗi khi nâng cấp. Dùng máy ảo thử với **bản N đang cài**:

1. Tạo cấu hình/log/data bằng bản N.
2. Cài bản N+1 theo đường nâng cấp được sản phẩm hỗ trợ.
3. Kiểm tra launcher, modules, resources, JVM options, shortcuts và file associations mới.
4. Kiểm tra format/migration dữ liệu user; không tự xóa dữ liệu ngoài yêu cầu.
5. Kiểm tra rollback/downgrade **nếu** sản phẩm có hỗ trợ.
6. Uninstall; xác nhận binaries và registration được gỡ đúng.
7. Kiểm tra những files user vẫn được giữ hoặc xóa theo chính sách công bố.

Windows MSI, macOS installer và Linux package managers có cơ chế riêng. **Đừng lấy một luật upgrade của hệ này áp cho hệ kia.**

## 14. Những nguyên nhân đóng gói lỗi thường gặp

### 14.1. “ClassNotFound” sau khi tạo image

Kiểm tra `--main-jar` relative path trong `--input`, `--main-class` đầy đủ, JAR thực tế trong image, dependencies/module path và launcher config. Nếu IDE classpath khác packaged JAR, chạy trong IDE không thể đại diện cho package.

### 14.2. Resource có trong source nhưng vắng mặt trong image

`Class.getResourceAsStream` có thể trả `null`. Dùng `jar --list` kiểm tra JAR **đã được đưa vào app-image**; đừng dùng absolute path `src/main/resources` chỉ tồn tại trên developer machine.

### 14.3. JVM mới nhưng runtime không có provider

Với custom runtime hoặc JDK 25+ default service-binding behavior, `ServiceLoader` có thể không tìm được provider mà code mong đợi. Xác định modules/service providers và thử `--jlink-options --bind-services` khi đúng nhu cầu.

### 14.4. Native library vắng mặt hoặc sai kiến trúc

Thư viện DLL/`.so`/`.dylib` có liên hệ với OS/arch; có thể phát sinh `UnsatisfiedLinkError`. Kiểm tra native dependencies, OS release, system libraries, signing và packaging layout.

### 14.5. App mở được từ terminal nhưng không từ shortcut

Working directory, env vars, arguments hoặc permissions có thể khác. Dùng file logger/runtime diagnostics và test trên chính shortcut được installer tạo.

### 14.6. Chạy được khi admin nhưng không chạy bằng user thường

Có thể app đang ghi `Program Files` hoặc không có quyền tạo log/cache. Chọn writable user-data directory; không coi elevation vĩnh viễn là cách sửa mặc định.

### 14.7. App image chạy nhưng MSI/DMG/DEB không cài được

Các giai đoạn khác nhau. Installer còn tạo registration, shortcuts, package metadata và chịu policy OS. Đọc **installer logs** và test trên target OS, không sửa Java code theo suy đoán.

### 14.8. Copy riêng EXE ra ngoài thư mục

Launcher còn cần JAR, config và runtime. **Di chuyển toàn bộ image**, không chỉ một executable. Trong demo, di chuyển image cả bộ vẫn chạy được với exit 0.

## 15. Test matrix chấp nhận phát hành

| ID | Phép thử | Kỳ vọng |
| --- | --- | --- |
| P01 | `javac --release N` và unit tests | Source/API/bytecode đạt mức cam kết |
| P02 | `jar --list` + resource checksum | Class và resources thực sự trong JAR |
| P03 | `jpackage --type app-image` trên target OS | Image tạo với launcher và runtime |
| P04 | Launcher mặc định | Java main nhận default args và JVM options |
| P05 | Launcher với một argument có dấu cách | Java nhận đúng một argument |
| P06 | Chạy từ working directory khác | Không phụ thuộc CWD của IDE |
| P07 | Di chuyển toàn bộ image | Launcher vẫn thấy payload/runtime |
| P08 | Máy không có JDK ngoài | Image vẫn chạy self-contained |
| P09 | Thư mục user-data writable, install dir read-only | App không đòi ghi vào install dir |
| P10 | ServiceLoader, reflection, JNI, network/TLS dùng thật | Runtime/modules/providers/native libs đủ |
| P11 | Native MSI/EXE/DMG/PKG/DEB/RPM | Cài được trên OS/arch đã hỗ trợ |
| P12 | Shortcut, file association, alternative launchers | Đúng entrypoint và quyền |
| P13 | Signature/notarization/repo policy | Artifact cuối qua security controls |
| P14 | Install bản N rồi nâng N+1 | Không mất data ngoài chính sách |
| P15 | Uninstall | Gỡ đúng files/registration và quản lý data |
| P16 | Kiểm thử distro/CPU khác trong support matrix | Mỗi target có bằng chứng độc lập |

**Tình trạng kiểm chứng của ví dụ bài này:** P02–P07 đã được thử trên **Windows x64/OpenJDK 24.0.2** với app-image. Các phép thử MSI/macOS/Linux/install/update/uninstall là checklist và quy trình **chưa chạy** trong bài, nên không được đánh dấu PASS giả.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Có thể từ Windows build trực tiếp `jpackage --type dmg` và gửi cho người dùng Mac không?

**Đáp án:** Không. Native package phải được tạo trên target OS; phải dùng macOS runner cho DMG/PKG.

**Câu 2.** Tại sao `java -jar app.jar` PASS không chứng minh `app.exe` PASS?

**Đáp án:** Nó dùng Java runtime/classpath của môi trường gọi lệnh, chưa thử native launcher, bundled runtime hoặc config thực tế của app-image.

**Câu 3.** `--type app-image` đã kiểm tra install/uninstall native chưa?

**Đáp án:** Chưa. Nó chỉ tạo thư mục ứng dụng runnable, không thực hiện cài vào OS package system.

**Câu 4.** Bản build `--release 17` có bắt buộc đóng kèm runtime JDK17 không?

**Đáp án:** Không. Compiler target và runtime do `jpackage` tạo là hai yếu tố khác nhau; cần đọc `java.home` và metadata của image thật.

**Câu 5.** Vì sao từ JDK 25 cần chú ý `--bind-services`?

**Đáp án:** `jpackage` không còn tự bao gồm service bindings mặc định như trước; cần thêm provider modules khi code/ServiceLoader thực sự yêu cầu và test đủ use cases.

**Câu 6.** Vì sao thử di chuyển **toàn bộ** image?

**Đáp án:** Để phát hiện dependencies/hardcoded paths còn trỏ tới workspace build; không thể thử bằng cách copy riêng launcher.

**Câu 7.** Muốn kiểm tra JAR đã vào image nguyên vẹn, dùng gì?

**Đáp án:** Kiểm tra `app/app.jar` và so sánh SHA-256 giữa input JAR và JAR đóng gói; vẫn phải chạy launcher để xác nhận hoạt động.

**Câu 8.** Những test Windows nào cần VM thay vì chỉ app-image?

**Đáp án:** MSI/EXE install, UAC/permissions, per-user/per-machine scope, upgrade, uninstall, registry/shortcut, signed artifact behavior.

**Câu 9.** macOS `codesign --verify` thành công có tự chứng minh đã notarized không?

**Đáp án:** Không. Code signing và notarization/Gatekeeper là những kiểm tra riêng theo chính sách phân phối.

**Câu 10.** Một `deb` chạy trên Ubuntu có thể được báo PASS cho mọi bản Linux không?

**Đáp án:** Không. Cần thử đúng distro/OS/architecture đã cam kết, bao gồm dependencies và package-manager behavior.

**Câu 11.** App lỗi ghi log sau cài nhưng chạy tốt khi admin; điều gì đáng kiểm tra?

**Đáp án:** User account, nơi ghi log/cache/config và ACL; đừng mặc định nâng quyền để che lỗi dùng install directory như vùng writable.

**Câu 12.** Trong Windows demo, vì sao `args=[from-package]` rồi `args=[North Region]`?

**Đáp án:** `--arguments from-package` chỉ áp dụng khi không truyền CLI arguments. Khi truyền `"North Region"`, arguments của user thay thế defaults.

**Câu 13.** Tại sao `jpackage --verbose` không giúp chẩn đoán mọi crash sau vài ngày sử dụng?

**Đáp án:** Nó log **build**, không ghi runtime events của app sau khi phát hành. Cần application logs, OS diagnostics và crash reports.

**Câu 14.** Vì sao artifact self-contained vẫn cần cập nhật runtime?

**Đáp án:** Runtime nằm **bên trong package**, không tự nâng cấp khi hệ điều hành hoặc Java ngoài máy được cập nhật. Nhà phát hành phải rebuild/redeploy.

## 17. Checklist kết luận

- [ ] Xác định OS, release, CPU architecture và package type thật sự được hỗ trợ.
- [ ] Build native package bằng `jpackage` trên đúng target OS, không giả định cross-platform packaging.
- [ ] Phân biệt source release, JDK compiler, JDK packager và bundled runtime version.
- [ ] Kiểm tra JAR/module/resources được đóng gói đủ, không phụ thuộc IDE classpath.
- [ ] Chạy `--type app-image` trước installer và thực thi native launcher thật.
- [ ] Thử default/user arguments, JVM properties, bundled runtime, resource loading và exit code.
- [ ] Thử đường dẫn có dấu cách/Unicode, cwd khác, di chuyển toàn bộ image.
- [ ] Test trên hệ thống không dựa vào JDK/JRE ngoài và tài khoản user thường.
- [ ] Xác minh modules, ServiceLoader/providers, JNI/native libraries/TLS mà app dùng.
- [ ] Với JDK 25+, cân nhắc service binding thay đổi và `--jlink-options --bind-services` nếu cần.
- [ ] Build/test từng MSI/EXE/PKG/DMG/DEB/RPM trên OS phù hợp với native tools cần thiết.
- [ ] Kiểm tra install scope, shortcut, permissions, signing/notarization, package metadata.
- [ ] Test reinstall, upgrade N→N+1, uninstall và chính sách user data.
- [ ] Lưu build/installer/runtime logs riêng, kiểm soát secrets và ghi đúng exit codes.
- [ ] Lưu checksum và metadata của **artifact cuối cùng** sẽ phát hành.
- [ ] Không nâng quyền vô điều kiện hay tắt bảo vệ hệ thống chỉ để vượt test.
- [ ] Chỉ ghi PASS cho OS/architecture/format đã được kiểm chứng thực tế.
- [ ] Có kế hoạch rebuild app-image khi bundled runtime cần security patch.

## 18. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html): quy tắc build trên target platform, các format, app image và bundled runtime, thay đổi service bindings từ JDK25.
2. [Oracle Java SE 26 — Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/26/jpackage/index.html): hướng dẫn app-image, native installer, launchers và quản lý cài đặt.
3. [Oracle Java SE 25 — jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): `--type`, `--main-jar`, `--arguments`, `--java-options`, `--runtime-image`, `--jlink-options` và các options theo OS.
4. [Oracle Java SE 26 — jlink Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): custom runtime và service binding.
5. [Oracle Java SE 26 — Support Application Requirements](https://docs.oracle.com/en/java/javase/26/jpackage/support-application-features.html): additional launchers, file associations và macOS signing.
6. [Oracle Java SE 26 — Manage the Installation](https://docs.oracle.com/en/java/javase/26/jpackage/manage-installation.html): quản lý install dir, shortcuts và tùy chọn OS.
7. [OpenJDK — JEP 392](https://openjdk.org/jeps/392): jpackage từ incubator thành production-ready ở JDK16.
8. [Microsoft Learn — Windows Installer Command-Line Options](https://learn.microsoft.com/en-us/windows/win32/msi/command-line-options): `msiexec /L*v` để thu log cài MSI.
9. [Apple Developer — Notarizing macOS Software Before Distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution): notarization và macOS distribution.
