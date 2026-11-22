# Đường dẫn có khoảng trắng, quyền truy cập và nhật ký khởi chạy của gói cài đặt Java

## 1. Tổng quan

Khi đóng gói ứng dụng Java bằng `jpackage` thành **application image** hoặc **installer native**, ba nhóm lỗi rất dễ bị nhầm là:

- **Path có dấu cách**: thư mục như `C:\Build Workspace\My App\input files`, `C:\Program Files\Example Vendor` và tên launcher `Space Log App.exe` cần được truyền đúng thành **một đối số** qua command shell.
- **Quyền truy cập**: quyền để **build**, quyền để **cài package** và quyền để **ứng dụng ghi file khi chạy** là những việc khác nhau. Một app cài thành công ở `Program Files` chưa chắc được phép ghi log ngay bên cạnh JAR.
- **Nhật ký**: `jpackage --verbose` ghi chẩn đoán lúc **build**, `msiexec /L*v` dành cho cài **MSI trên Windows**, còn nhật ký **khởi chạy** phải đến từ console hoặc logger trong ứng dụng. Ba loại log không thể thay nhau.

Bài học hướng dẫn kỹ thuật còn được hỗ trợ trong các JDK hiện hành. `jpackage` có từ Java 14 ở giai đoạn incubating và **chính thức production-ready từ Java 16 (JEP 392)**; thực hành sử dụng API ổn định Java 17+ và công cụ `jpackage` hiện đại, **không dùng module incubator cũ**.

## 2. Ba giai đoạn của một gói Java

```text
Source code + JAR + resources
         |
         v
BUILD: javac / jar / jpackage
  --input, --main-jar, --dest, --temp
  Log: --verbose và staging directory
         |
         v
INSTALL: MSI/EXE hoặc PKG/DMG/DEB/RPM
  Install scope, filesystem permissions, policy
  Log: cơ chế riêng của installer/OS
         |
         v
RUN: native launcher -> Java runtime -> main()
  Classpath/modules, args, working directory
  Log: stdout/stderr hoặc application file log
```

| Triệu chứng | Tầng cần kiểm tra đầu tiên | Thông tin cần có |
| --- | --- | --- |
| `jpackage` không tìm thấy `app.jar` | Build | Path `--input` và `--main-jar` |
| `jpackage` không tạo được output | Build | Quyền ghi `--dest`/`--temp`, `--verbose` |
| MSI báo lỗi hoặc rollback | Install | MSI verbose log, quyền cài, exit code |
| Double-click ứng dụng không phản hồi | Run | Launcher, console, app startup log |
| App chạy ở IDE nhưng không chạy ở shortcut | Run | Working directory, resources và runtime |
| Chỉ chạy bằng quyền administrator | Run hoặc install | ACL, nơi app ghi dữ liệu |
| Không tìm thấy log | Phụ thuộc giai đoạn | Có tạo đúng loại log chưa? |

Một **app image được build thành công** chưa chứng minh rằng **installer sẽ cài thành công**. Tương tự, installer thành công chưa chứng minh người dùng thường có quyền ghi file runtime.

## 3. Path chứa dấu cách: cách truyền đối số đúng

Những đường dẫn sau hoàn toàn bình thường:

```text
C:\Build Workspace\My Java App\input files\app.jar
C:\Build Workspace\My Java App\output image\
C:\Program Files\Example Vendor\Space Log App\
C:\Users\Example User\AppData\Local\Example Vendor\Space Log App\logs\
```

**Sai trong PowerShell:**

```powershell
# CỐ Ý SAI: khoảng trắng tách --input thành nhiều phần.
jpackage --input C:\Build Workspace\input files --name Demo

# CỐ Ý SAI: executable path bị chia tách.
C:\Program Files\Example Vendor\Space Log App.exe
```

**Đúng:** dùng biến chứa path và gọi executable bằng `&`:

```powershell
$inputDir = "C:\Build Workspace\My Java App\input files"
$destDir = "C:\Build Workspace\My Java App\output image"

jpackage --type app-image --name "Space Log App" --input $inputDir --dest $destDir --main-jar app.jar --main-class demo.SpaceLogMain

$launcher = "C:\Program Files\Example Vendor\Space Log App\Space Log App.exe"
& $launcher
& $launcher "North Region"
```

Trong lệnh cuối, `"North Region"` là **một đối số của ứng dụng**, không phải hai đối số `North` và `Region`.

### 3.1. Argument array là lựa chọn an toàn hơn cho lệnh dài

```powershell
$options = @(
    "--type", "app-image",
    "--name", "Space Log App",
    "--input", "C:\Build Workspace\My Java App\input files",
    "--dest", "C:\Build Workspace\My Java App\output image",
    "--main-jar", "app.jar",
    "--main-class", "demo.SpaceLogMain",
    "--win-console"
)

& jpackage @options
```

`@options` là **PowerShell array splatting**. Mỗi phần tử là một argument, làm giảm rủi ro tách nhầm dấu cách. Không ghép một chuỗi command từ user input rồi dùng `Invoke-Expression`; cách đó có nguy cơ command injection và sai quoting.

Đặc biệt, `--arguments` của `jpackage` có quy tắc phân tích **arguments mặc định** riêng. Nếu giá trị mặc định có dấu cách, cần kiểm thử launcher thực để xác nhận số phần tử `String[] args`. Truyền path có dấu cách vào một option và khai báo **nhiều arguments mặc định** là hai vấn đề quoting khác nhau.

### 3.2. Java `Path` không cần quote kiểu shell

```java
import java.nio.file.Path;

Path file = Path.of("C:\\Build Workspace\\My Java App\\data.txt");
```

Đây là đoạn minh họa trong Java method. `Path.of` nhận **giá trị path**, không nhận một lệnh shell; không tự đưa dấu nháy kép vào đầu/cuối path để “escape spaces”. Hai dấu backslash trong Java string literal tạo **một** backslash thật.

Khi Java cần gọi process khác, dùng argument list:

```java
Process process = new ProcessBuilder(
        executable.toString(),
        "--file", inputFile.toString(),
        "--region", "North Region"
).start();
```

Đoạn này yêu cầu biến `executable` và `inputFile` kiểu `Path` đã có. `ProcessBuilder` truyền riêng từng argument, không yêu cầu bạn tự nối command string cho shell.

### 3.3. Linux/macOS dùng quy tắc quoting khác

```bash
input_dir="$HOME/Build Workspace/input files"
dest_dir="$HOME/Build Workspace/output image"

jpackage --type app-image --name "Space Log App" --input "$input_dir" --dest "$dest_dir" --main-jar app.jar --main-class demo.SpaceLogMain
```

Với POSIX shell, nhớ **quote biến** `"$input_dir"` khi có dấu cách. `jpackage` không đóng gói native installer xuyên hệ điều hành: chạy công cụ trên **OS đích** để tạo dạng package tương ứng.

## 4. Những vị trí đường dẫn quan trọng của `jpackage`

| Option | Chỉ tới | Quy tắc |
| --- | --- | --- |
| `--input` | Thư mục chứa JAR/resources đầu vào | Phải tồn tại, có quyền đọc |
| `--main-jar` | JAR chính **tương đối với `--input`** | `app.jar` phải nằm bên trong input |
| `--dest` | Thư mục chứa image/installer được tạo | Phải ghi được |
| `--temp` | Thư mục tạm **mới hoặc rỗng** | Cần ghi được; được giữ lại khi chỉ định |
| `--runtime-image` | Runtime tạo sẵn nếu dùng | Đúng OS/architecture, đủ modules |
| `--install-dir` | Vị trí cài **native package** | Không phải vị trí log runtime |
| `--icon` | File icon đầu vào | Path và định dạng hợp lệ |

Với `--temp`, công cụ yêu cầu một thư mục mới/rỗng và **giữ staging sau khi build** để phục vụ chẩn đoán. Nếu không đặt `--temp`, công cụ thường tạo và dọn thư mục tạm tự động. Staging có thể chứa path và cấu hình nội bộ; đừng lưu vĩnh viễn hoặc đặt trong nơi công khai.

### 4.1. Địa chỉ cài đặt khác nhau theo OS

- **Windows:** `--install-dir` là **đường dẫn con tương đối** trong vùng cài đặt. `--win-dir-chooser` có thể thêm hộp thoại chọn directory khi cài installer Windows.
- **Linux/macOS:** có thể dùng đường dẫn **tuyệt đối** phù hợp với hệ thống và package.
- **`--type app-image`:** tạo thư mục ứng dụng có thể chạy, **không thực hiện cài đặt**. Các quyền/installer options chỉ được thử đầy đủ khi tạo native package.

Ví dụ tạo MSI Windows (**chỉ minh họa, không được thực thi trong bài test**):

```powershell
$installerOptions = @(
    "--type", "msi",
    "--name", "Space Log App",
    "--input", "C:\Build Workspace\My App\input files",
    "--dest", "C:\Build Workspace\My App\packages",
    "--main-jar", "app.jar",
    "--main-class", "demo.SpaceLogMain",
    "--install-dir", "Space Log App",
    "--win-dir-chooser"
)

jpackage @installerOptions
```

Cần có **công cụ packaging native** mà JDK yêu cầu (Windows thường dùng WiX). Không nhầm `--type msi` với `--type app-image`; các quyền cài đặt chỉ phát sinh khi thực sự chạy installer.

## 5. Quyền truy cập: build, install và run phải được kiểm tra riêng

### 5.1. Quyền BUILD

Build cần quyền **đọc** JAR/resources và quyền **ghi** vào `--dest`/`--temp`. Có thể thất bại do ACL, policy, disk full hoặc file-lock. Nên build trong workspace user có quyền, ghi log `--verbose`, và điều tra path thật trước khi nâng quyền của toàn bộ pipeline.

### 5.2. Quyền INSTALL

`C:\Program Files` thường là vị trí hệ thống được bảo vệ. Installer per-machine có thể cần quyền nâng cao theo policy. Với Windows, `jpackage` hỗ trợ **`--win-per-user-install`** để yêu cầu cài theo tài khoản người dùng hiện tại khi phù hợp.

**Không mặc định rằng per-user luôn tránh quyền admin:** UAC, group policy, service registration, file association và các thao tác đặc biệt khác có thể còn yêu cầu quyền.

| Tình huống | Điều cần làm |
| --- | --- |
| Cài per-machine | Xem quyền destination, policy, UAC và log installer |
| Cài per-user Windows | Cân nhắc `--win-per-user-install`, thử bằng user thường |
| Chọn nơi cài | Dùng `--win-dir-chooser` nếu cần, kiểm thử path có dấu cách |
| Đăng ký service | Đánh giá tài khoản service và quyền của nó |
| Linux DEB/RPM hay macOS PKG | Tuân thủ quyền package manager và chính sách OS |

Không sửa quyền `Program Files` thành writable cho mọi người để chữa sự cố log hoặc shortcut.

### 5.3. Quyền RUN

**Không đặt file mutable ngay cạnh JAR/runtime** trong thư mục cài đặt nếu ứng dụng chạy bằng tài khoản thường. Tránh:

```java
// CỐ Ý MINH HỌA THIẾT KẾ DỄ LỖI:
Files.writeString(Path.of("startup.log"), "started");
```

`"startup.log"` là **path tương đối theo working directory** (`user.dir`); không chắc nằm trong image hoặc user-data directory. Khi mở bằng shortcut, service hoặc terminal khác, working directory có thể thay đổi.

Tách:

- **Read-only assets:** JAR, templates, runtime, config mặc định đóng gói trong image.
- **Writable state:** logs, cache, data/config do user cập nhật; phải đặt ở thư mục được cấp quyền.

| OS | Vị trí thường phù hợp với log/dữ liệu user |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Vendor\Product\logs` |
| macOS | `~/Library/Logs/Product` hoặc Application Support |
| Linux | `$XDG_STATE_HOME/product` hoặc `~/.local/state/product` khi biến XDG không đặt |
| Service | Thư mục do admin cấp quyền cho service account, không mặc định user desktop |

Đây là **quy ước**, không phải cam kết mọi path luôn writable. Ứng dụng phải tạo thư mục và xử lý `IOException`/`AccessDeniedException` đúng cách.

**Chạy được khi admin chưa phải cách sửa:** có thể code đang ghi vào thư mục cài đặt bị bảo vệ. Thường nên sửa vị trí ghi thay vì yêu cầu elevated privileges cho mọi lần mở.

## 6. Phân biệt ba lớp nhật ký

### 6.1. Build log: `jpackage --verbose`

`--verbose` giúp xem các bước của công cụ packaging. Ví dụ PowerShell với `$options` đã khai báo:

```powershell
$buildLog = "C:\Build Workspace\My App\jpackage-build.log"

& jpackage @options --verbose 2>&1 |
    Out-File -FilePath $buildLog -Encoding utf8

if ($LASTEXITCODE -ne 0) {
    throw "jpackage build failed; inspect build log"
}
```

Kiểm tra **exit code**, không chỉ nhìn file log có tồn tại. Trong PowerShell 5.1, một số dòng output native có thể đi qua stderr; điều đó không tự chứng minh build thất bại.

**`--verbose` không ghi lỗi Java main khi người dùng mở app sau cài đặt.** Dùng `--temp` để giữ staging hỗ trợ điều tra build, rồi dọn có kiểm soát khi không cần.

### 6.2. Install log: Windows Installer MSI

Với một **MSI thực sự**, Microsoft hỗ trợ log cài đặt verbose:

```cmd
mkdir "C:\Install Logs"
msiexec.exe /i "C:\Install Packages\Space Log App.msi" /L*v "C:\Install Logs\Space Log App-install.log"
```

- `/i` bắt đầu cài package MSI.
- `/L*v` ghi thông tin và verbose logging.
- **Thư mục chứa log phải tồn tại trước**; MSI không tự tạo các thư mục cha của log.
- Path MSI và path log chứa khoảng trắng phải được quote.

**Không chạy lệnh cài trong môi trường không được phép**. Ví dụ này minh họa chẩn đoán, không phải một bước đã thử trong bài. `msiexec /L*v` **không dùng chung cho mọi installer EXE** hoặc một app-image folder; EXE wrapper có thể có tùy chọn riêng.

### 6.3. Runtime log: console hoặc logger Java

Windows CLI launcher có thể được tạo với option `--win-console`, cho phép quan sát `System.out`, `System.err` và stack trace khi gọi từ terminal. Nó **không tự tạo file log**.

```powershell
$launcher = "C:\Program Files\Example Vendor\Space Log App\Space Log App.exe"
$runLog = Join-Path $env:TEMP "space-log-app-run.log"

& $launcher "North Region" *> $runLog
$exitCode = $LASTEXITCODE

Get-Content -LiteralPath $runLog
Write-Output "exitCode=$exitCode"
```

Redirection có tác dụng khi launcher có **console stdout/stderr**. Với GUI launcher được double-click, không nên phụ thuộc terminal để có log: hãy **tự ghi file logger** từ đầu `main` vào thư mục writable.

Nếu lỗi xảy ra **trước khi Java main chạy** (thiếu runtime, JAR, main class hoặc launcher hỏng), logger Java **chưa có cơ hội tạo file**. Khi đó cần kiểm tra launcher, console, OS diagnostics và nội dung image.

| Log | Tầng | Dùng cho |
| --- | --- | --- |
| `jpackage --verbose` | Build | Input, staging, jlink, package creation |
| `msiexec /L*v` | MSI install | Quyền, rollback, installer actions |
| stdout/stderr | Launcher/Java khi chạy | Exceptions, thông báo trực tiếp |
| `startup.log` của app | Java main sau khi chạy | Cấu hình và trạng thái khởi tạo |

Tất cả log có thể chứa path, arguments hoặc dữ liệu nhạy cảm. Cần kiểm soát quyền đọc, giới hạn kích thước, rotation và retention.

## 7. Chương trình Java 17+ độc lập ghi nhật ký lúc khởi chạy

Để thử quyền ghi mà **không cần ghi vào app image**, chương trình chọn:

1. Biến `APP_DEMO_LOG_ROOT` nếu người kiểm thử đã khai báo.
2. Nếu không có, biến `LOCALAPPDATA` trên Windows.
3. Nếu vẫn không có, `user.home` làm fallback của demo.

Sau đó tạo `Example Vendor/Space Log App/logs/startup.log`. Cách này minh họa việc dùng vùng dữ liệu ngoài image; trong sản phẩm thật, chọn đường dẫn theo OS và dùng logging framework với rotation/locking.

Lưu thành file **`src/demo/SpaceLogMain.java`**:

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class SpaceLogMain {
    public static void main(String[] args) throws Exception {
        String configured = System.getenv("APP_DEMO_LOG_ROOT");
        String local = System.getenv("LOCALAPPDATA");

        Path base = configured != null && !configured.isBlank()
                ? Path.of(configured)
                : Path.of(local != null && !local.isBlank()
                        ? local : System.getProperty("user.home"));

        Path logDir = base.resolve("Example Vendor")
                .resolve("Space Log App").resolve("logs");
        Files.createDirectories(logDir);

        Path log = logDir.resolve("startup.log");
        Files.writeString(log,
                "start; args=" + String.join("|", args)
                        + System.lineSeparator(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);

        System.out.println("argv=" + Arrays.toString(args));
        System.out.println("logPresent=" + Files.isRegularFile(log));
        System.out.println("cwdHasSpaces="
                + System.getProperty("user.dir").contains(" "));
        System.err.println("diagnostic=stderr-available");
    }
}
```

**Giải thích:**

- `Path.resolve(...)` tạo path từ các thành phần, không tự thêm shell quotes.
- `Files.createDirectories(...)` tạo thư mục cha, hoặc báo lỗi nếu thiếu quyền.
- `Files.writeString(..., CREATE, APPEND)` tạo log hoặc append một dòng.
- `cwdHasSpaces` chỉ là một check phục vụ test, **không phải phép xác thực quyền**.
- `System.err` giúp so sánh cách quan sát runtime qua console.

**Bảo mật:** demo cố tình ghi arguments để chứng minh quoting. Trong production **không log token, mật khẩu hoặc arguments chứa dữ liệu nhạy cảm**. Nếu log ghi thất bại, xử lý `IOException`/`AccessDeniedException` rõ ràng; không âm thầm bỏ qua.

## 8. Build và kiểm thử với nhiều path chứa khoảng trắng

Dự án có cấu trúc:

```text
jpackage example <id>/
  source code/demo/SpaceLogMain.java
  compiled classes/
  input files/app.jar
  output image/
  build scratch/
  user data with spaces/
  other cwd/
```

### 8.1. Tạo workspace và biên dịch

Trong PowerShell, tạo một workspace riêng có GUID để tránh reuse staging:

```powershell
$root = Join-Path $env:TEMP (
    "jpackage example " + [guid]::NewGuid().ToString("N")
)

$sourceDir = Join-Path $root "source code\demo"
$classes = Join-Path $root "compiled classes"
$input = Join-Path $root "input files"
$dest = Join-Path $root "output image"
$scratch = Join-Path $root "build scratch"
$userData = Join-Path $root "user data with spaces"
$otherCwd = Join-Path $root "other cwd"

foreach ($d in @($sourceDir,$classes,$input,$dest,
                 $scratch,$userData,$otherCwd)) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

# Lưu source Java mục 7 vào file sau trước khi chạy javac.
$sourceFile = Join-Path $sourceDir "SpaceLogMain.java"

javac --release 17 -d $classes $sourceFile
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

jar --create --file (Join-Path $input "app.jar") -C $classes .
if ($LASTEXITCODE -ne 0) { throw "jar failed" }
```

`--main-jar app.jar` ở bước sau là path **tương đối với `--input`**, không cần đưa absolute path của developer.

### 8.2. Tạo app image

```powershell
$jpArgs = @(
    "--type", "app-image",
    "--name", "Space Log App",
    "--input", $input,
    "--dest", $dest,
    "--temp", $scratch,
    "--main-jar", "app.jar",
    "--main-class", "demo.SpaceLogMain",
    "--arguments", "boot",
    "--win-console",
    "--verbose"
)

$buildLog = Join-Path $root "jpackage verbose build.log"

& jpackage @jpArgs 2>&1 |
    Out-File -FilePath $buildLog -Encoding utf8

if ($LASTEXITCODE -ne 0) {
    throw "jpackage failed; inspect build log"
}

$launcher = Join-Path $dest "Space Log App\Space Log App.exe"
Test-Path -LiteralPath $launcher
```

**Đã chạy thử trên Windows/JDK 24.0.2:** app-image tạo được native `Space Log App.exe` trong path nhiều dấu cách. File build log tồn tại, `--temp` được giữ lại, `javac --release 17` và `jar` đều thành công. Việc tạo app image **không yêu cầu cài MSI/EXE installer**, nên kết quả thử này không thay cho test quyền cài đặt.

### 8.3. Chạy từ một working directory khác

```powershell
$env:APP_DEMO_LOG_ROOT = $userData

Push-Location $otherCwd
try {
    & $launcher
    Write-Output "exit=$LASTEXITCODE"

    & $launcher "North Region"
    Write-Output "exit=$LASTEXITCODE"
}
finally {
    Pop-Location
}

$startupLog = Join-Path $userData (
    "Example Vendor\Space Log App\logs\startup.log"
)
Get-Content -LiteralPath $startupLog
```

**Kết quả lần chạy không truyền argument:**

```text
argv=[boot]
logPresent=true
cwdHasSpaces=true
diagnostic=stderr-available
exit=0
```

**Kết quả khi truyền một argument có dấu cách:**

```text
argv=[North Region]
logPresent=true
cwdHasSpaces=true
diagnostic=stderr-available
exit=0
```

**Nội dung file `startup.log`:**

```text
start; args=boot
start; args=North Region
```

Hai stream stdout/stderr có thể đổi thứ tự hiển thị vì buffering, nhưng từng dòng và **exit code 0** đã được kiểm chứng. `--arguments boot` chỉ là arguments **mặc định khi không có arguments người dùng**. Khi gọi `& $launcher "North Region"`, phần mặc định bị thay thế, nên Java thấy một phần tử `args[0] = "North Region"`.

### 8.4. Vì sao bài test này có giá trị?

- `--input`, `--dest`, `--temp`, tên app và file exe đều có dấu cách nhưng vẫn build/run được.
- Code không dựa vào working directory của IDE.
- File log được tạo trong `APP_DEMO_LOG_ROOT` chứ không đòi quyền ghi vào app-image.
- Kết quả hai lần chạy đã xác nhận default arguments và user-supplied arguments.
- Build log và runtime log tách biệt rõ; có thể đối chiếu hai giai đoạn độc lập.

Trong triển khai thật cần test thêm **installer native** và **tài khoản không có quyền administrator** trên hệ điều hành đích.

## 9. Resource loading và working directory

Sai lầm rất thường gặp là dùng path tương đối cho một resource đóng gói:

```java
Path config = Path.of("config/default.properties");
```

Đường dẫn này dựa vào `user.dir`, không chắc trỏ vào JAR/image sau khi mở qua shortcut hoặc service. Với resource có bên trong JAR, dùng classpath resource API:

```java
try (var in = SpaceLogMain.class
        .getResourceAsStream("/config/default.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing packaged resource");
    }
    // Đọc input stream.
}
```

Đây là đoạn minh họa, yêu cầu tài nguyên tương ứng thực sự nằm trong JAR và trong ứng dụng modular cần tôn trọng encapsulation. Với config do user chỉnh sửa, hãy đặt ở user-data directory chứ không ghi ngược vào JAR.

## 10. Quy trình chẩn đoán lỗi theo thứ tự

1. **Xác định giai đoạn:** `jpackage` thất bại khi build, installer không cài được, hay launcher không chạy được?
2. **Xác nhận path và argument:** truyền mỗi path làm một đối số; test executable từ terminal với `& $launcher` và tham số có dấu cách.
3. **Kiểm tra mã lỗi:** xem `$LASTEXITCODE` của `javac`, `jar`, `jpackage`, launcher hoặc installer.
4. **Thu đúng log:** build `--verbose`; MSI `/L*v`; runtime console/app logger. Một log không thay thế được loại khác.
5. **Xác nhận quyền:** nơi input có đọc được, staging/dest có ghi được, installer có đúng scope, runtime có quyền viết user-data dir.
6. **Xem resource/dependency:** các JAR/modules/libraries có được đóng gói, và code có phụ thuộc cwd/IDE không?
7. **Dùng positive test:** chạy từ path có dấu cách và user thường, tạo file log ở nơi đã cấp quyền, đối chiếu exit code.
8. **Sửa đúng tầng:** điều chỉnh path, ACL tối thiểu hoặc logic logger; không che lỗi bằng việc chạy elevated vô điều kiện.

| Lỗi | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Sai path, resource thiếu, cwd khác | Kiểm tra absolute path/resource API |
| `AccessDeniedException` | ACL/chính sách ngăn ghi | Chọn writable directory, xử lý lỗi |
| `jpackage` không nhận option | Tách args sai, dùng option khác OS | Dùng array, kiểm tra `jpackage --help` |
| Launcher không xuất hiện | Build/image lỗi hoặc path khác dự kiến | Đối chiếu `--dest`, verbose log |
| GUI không có log console | Không có console | Cấu hình file logger sớm |
| MSI rollback | Quyền cài hoặc installer action lỗi | Đọc `/L*v`, không nhầm build log |
| Chạy được khi admin | Thư mục protected bị ghi/đọc sai | Sửa vị trí file và scope quyền |

### 10.1. Những điều tuyệt đối không nên suy đoán

- Path có khoảng trắng **không đồng nghĩa** thiếu quyền; quoting sai và ACL sai là hai nhóm lỗi khác nhau.
- Installer cài thành công **không có nghĩa** mọi user được ghi vào thư mục cài đặt.
- File `jpackage-build.log` có tồn tại **không có nghĩa** build trả exit code 0.
- Không có `startup.log` **chưa chứng minh** `main` chưa chạy: có thể logger bị lỗi quyền.
- `--win-console` **không tự tạo** runtime log file.
- `msiexec /L*v` **không áp dụng** cho app-image và mọi EXE wrapper.
- Copy riêng native executable ra ngoài app image **không đủ**, vì nó còn phụ thuộc runtime và payload đi kèm.
- Test trên Windows **không chứng minh** bundle Linux/macOS có thể chạy: phải build/test theo host tương ứng.

## 11. Bài tập và đáp án

**Câu 1.** Làm sao truyền `C:\Build Workspace\input files` cho `--input`?

**Đáp án:** Quote toàn path hoặc dùng biến PowerShell `$inputDir`/argument array; không để shell tách thành nhiều argument.

**Câu 2.** Vì sao không nên ghi `startup.log` ở `C:\Program Files\Vendor\App`?

**Đáp án:** Tài khoản user thường có thể không có quyền ghi; nên dùng user-data/state/log dir phù hợp và xử lý `IOException`.

**Câu 3.** `--verbose` và `--win-console` khác nhau thế nào?

**Đáp án:** `--verbose` là chẩn đoán **build jpackage**, `--win-console` tạo Windows **console launcher** để quan sát output ứng dụng khi chạy.

**Câu 4.** Vì sao MSI bị lỗi cần `/L*v` chứ không chỉ đọc `jpackage --verbose`?

**Đáp án:** Build và install là hai giai đoạn khác nhau; MSI log ghi các action/quyền của Windows Installer.

**Câu 5.** `msiexec /L*v` có dùng cho một thư mục app-image không?

**Đáp án:** Không; nó dùng cho **MSI installation**, app-image chưa thực hiện quá trình này.

**Câu 6.** Chạy `& $launcher "North Region"`, Java main nhận bao nhiêu arguments?

**Đáp án:** Một argument `"North Region"`, như output `argv=[North Region]` trong demo.

**Câu 7.** `Path.of("config.txt")` có luôn trỏ vào thư mục chứa EXE không?

**Đáp án:** Không. Đường dẫn tương đối dựa vào current working directory, khác nhau theo cách khởi chạy.

**Câu 8.** `--win-per-user-install` có bảo đảm không cần admin trong mọi trường hợp không?

**Đáp án:** Không. Còn phụ thuộc install scope, policy và các thao tác hệ thống cụ thể.

**Câu 9.** Vì sao dùng `--temp` cần dọn sau khi gỡ lỗi?

**Đáp án:** Working directory được giữ lại sau build; nó có thể chiếm dung lượng và chứa thông tin path/cấu hình không nên lưu công khai.

**Câu 10.** Nếu app chạy được khi elevated mà không chạy được khi user thường, sửa thế nào?

**Đáp án:** Tìm hành động bị từ chối trong log/stack trace và chuyển dữ liệu writable tới vùng được cấp quyền; tránh mặc định yêu cầu chạy mọi lần bằng administrator.

## 12. Checklist trước khi phát hành

- [ ] Sử dụng `jpackage` production-ready, không dùng cú pháp incubator cũ.
- [ ] Test `--type app-image` trước khi phát hành installer native.
- [ ] Từng đường dẫn `--input`, `--dest`, `--temp`, JAR và launcher được truyền nguyên vẹn dù có dấu cách.
- [ ] Không dùng `Invoke-Expression` với command sinh từ user input.
- [ ] `--main-jar` là path tương đối với `--input` và file có thật.
- [ ] Test filename app, folder cài, current working directory và một CLI argument có dấu cách.
- [ ] Tách resources read-only khỏi log/config/cache writable.
- [ ] File log/runtime data nằm trong user-data directory hoặc nơi service account được cấp quyền.
- [ ] Test bằng tài khoản không nâng quyền; không mở rộng ACL `Program Files` tùy tiện.
- [ ] Bật `--verbose` để điều tra build; kiểm tra exit code và staging `--temp`.
- [ ] Với MSI, dùng đúng cú pháp logging Windows Installer và tạo sẵn parent folder.
- [ ] Với console launcher Windows, dùng `--win-console`; GUI cần file logger riêng.
- [ ] Không log bí mật; đặt rotation, retention và kiểm soát quyền truy cập log.
- [ ] Kiểm thử trên từng OS/architecture mục tiêu, không giả định cross-platform packaging.

## 13. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 25 — jpackage command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): các option `--input`, `--dest`, `--temp`, `--verbose`, `--install-dir`, `--win-console`, `--win-per-user-install`.
2. [Oracle Java SE 26 — Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/26/jpackage/index.html): app image, native installer và runtime.
3. [Oracle Java SE 25 — Manage the Installation](https://docs.oracle.com/en/java/javase/25/jpackage/manage-installation.html): nơi cài và launcher console.
4. [Microsoft Learn — Windows Installer Command-Line Options](https://learn.microsoft.com/en-us/windows/win32/msi/command-line-options): `/L*v` và yêu cầu tồn tại thư mục cha của MSI log.
5. [Microsoft Learn — Logging (Windows Installer)](https://learn.microsoft.com/en-us/windows/win32/msi/logging): logging và cảnh báo dữ liệu nhạy cảm.
6. [Oracle Java SE 17 — jpackage command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): cách dùng với JDK 17.
7. [OpenJDK — JEP 392](https://openjdk.org/jeps/392): jpackage chính thức từ JDK 16.
