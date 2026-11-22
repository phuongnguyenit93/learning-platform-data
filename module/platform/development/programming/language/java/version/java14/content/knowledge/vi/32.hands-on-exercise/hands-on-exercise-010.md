# Tạo app-image rồi kiểm thử gói cài đặt Java trên máy đích

## 1. Mục tiêu thực hành và phạm vi kết quả

Bài thực hành này đi từ **mã nguồn Java** tới **JAR**, sau đó tạo **app-image có Java runtime đi kèm**, cuối cùng tạo **native installer theo hệ điều hành** và xây dựng kịch bản kiểm thử khi người dùng cài trên máy đích. Đây là một bài thực hành tổng hợp: phải kiểm tra cả việc build, khởi chạy và cài/gỡ, không chỉ dừng ở lệnh đóng gói không báo lỗi.

Sau khi học, bạn cần biết cách:

1. Biên dịch và đóng gói JAR có điểm vào `main` và resource thực sự nằm trong artifact.
2. Dùng `jpackage --type app-image` để tạo launcher native và runtime Java đi kèm.
3. Chạy launcher khi `java`, `javac` không xuất hiện trên `PATH`, nhưng không nhầm đây là máy sạch thật sự.
4. Tạo installer `msi`/`exe` trên Windows, `deb`/`rpm` trên Linux hoặc `pkg`/`dmg` trên macOS, phù hợp với toolchain của từng nền tảng.
5. Chuyển installer sang VM/máy đích, kiểm thử **cài mới → khởi chạy → chức năng → nâng cấp nếu áp dụng → gỡ cài đặt**.
6. Lập biên bản PASS/FAIL/NOT RUN trung thực, tách bằng chứng đã kiểm chứng khỏi bước chưa chạy.

**Phiên bản hiện hành:** `jpackage` xuất hiện ở trạng thái incubating trong Java 14, nhưng **trở thành công cụ chuẩn từ JDK 16** (JEP 392). Bài sử dụng **JDK 17+**, không hướng dẫn module incubator hoặc flag preview Java 14 cũ. Ví dụ chính được kiểm chứng bằng OpenJDK 24 trên Windows với mã biên dịch `--release 17`. Các bước Linux, macOS và cài đặt trên VM sạch là hướng dẫn triển khai trên máy tương ứng, không phải kết quả đã thực thi trong môi trường Windows đó.

## 2. Phân biệt JAR, app-image và installer

| Đầu ra | Thành phần chính | Cách khởi động | Điều được xác minh |
| --- | --- | --- | --- |
| `app.jar` | Java class, manifest, resource và JAR dependency phù hợp | `java -jar app.jar` khi có Java runtime hệ thống | Mã Java và cấu trúc JAR |
| `app-image` | Launcher native + tệp ứng dụng + Java runtime image | Chạy launcher của hệ điều hành | Ứng dụng tự mang runtime, không cần `java` hệ thống |
| Native installer | Gói cài theo hệ điều hành, thường chứa app-image | Cài đặt qua OS, rồi mở ứng dụng đã cài | Hành vi phân phối, quyền, shortcut, upgrade, uninstall |

Một bộ app-image có cấu trúc khái quát:

```text
Windows:
PackageSmoke/
  PackageSmoke.exe
  app/
    app.jar
    PackageSmoke.cfg
  runtime/
    lib/
      modules

Linux:
PackageSmoke/
  bin/
    PackageSmoke
  lib/
    app/
      app.jar
    runtime/

macOS:
PackageSmoke.app/
  Contents/
    MacOS/
      PackageSmoke
    app/
      app.jar
    runtime/
```

Các vị trí file nội bộ có thể khác giữa các phiên bản JDK; sơ đồ chỉ để định hướng. **Không copy mỗi `.exe` hoặc riêng `.jar`** khi muốn phân phối app-image. Launcher phụ thuộc vào runtime và tệp kèm theo trong cây thư mục.

Nếu không cung cấp `--runtime-image`, `jpackage` dùng `jlink` để tạo runtime từ JDK đóng gói. Vì thế người dùng thường **không cần cài riêng JDK/JRE**, nhưng ứng dụng vẫn có JVM chạy ở **bên trong gói**. Java runtime nhúng không nhất thiết chứa `javac` hoặc toàn bộ công cụ lập trình.

**App-image chạy tốt chưa đủ chứng minh installer chạy tốt:** MSI/EXE/DEB/RPM/PKG/DMG có thêm chính sách cài đặt, quyền hệ thống, shortcut, signing, nâng cấp và gỡ. Mỗi giai đoạn có tiêu chí QA riêng.

## 3. Điều kiện hệ điều hành và toolchain

### Máy build

Máy build cần JDK có `javac`, `jar` và `jpackage` cùng các file ứng dụng. Đối với **native installer**, cần thêm công cụ đóng gói tương thích:

| Hệ điều hành build | Dạng gói | Điều kiện chính |
| --- | --- | --- |
| Windows | `app-image`, `msi`, `exe` | JDK, và **WiX tương thích** khi tạo MSI/EXE |
| Linux | `app-image`, `deb`, `rpm` | JDK và toolchain package phù hợp distro, có thể gồm `fakeroot` hoặc `rpm-build` |
| macOS | `app-image`, `pkg`, `dmg` | JDK, các công cụ macOS phù hợp; signing/notarization theo quy trình phát hành |

Kiểm tra trên máy build:

```powershell
java -version
javac -version
jar --version
jpackage --version
jpackage --help
```

Lệnh ở trên có thể chạy trong PowerShell Windows. `jpackage --help` giúp xác nhận những option được bản JDK hiện tại hỗ trợ. Những option bắt đầu bằng `--win-` chỉ dành cho Windows, còn `--mac-`/`--linux-` chỉ phù hợp nền tảng tương ứng.

**Không dùng Windows host để tạo trực tiếp native package Linux/macOS.** Java bytecode có thể tái sử dụng nhưng launcher và runtime image là native; mỗi OS và kiến trúc CPU phải có gói phù hợp.

### Máy đích

Máy đích cần OS/CPU tương thích, đủ thư viện native của hệ điều hành và quyền cài đặt/khởi động phù hợp. Nó không phải cài JDK riêng nếu image thực sự kèm runtime đủ chức năng. Nhưng vẫn có thể cần driver, GUI libraries, C runtime, font, network hoặc dịch vụ ngoài tùy ứng dụng.

Tách rõ hai mức test:

- **Mức A – trên máy build:** tạm bỏ lệnh `java`/`javac` khỏi `PATH` và biến `JAVA_HOME`; gọi launcher theo đường dẫn tuyệt đối. Máy vẫn còn JDK trên đĩa.
- **Mức B – máy sạch thật:** chuyển installer sang VM/host không cài sẵn JDK/JRE hệ thống, cài và chạy đúng cách người dùng cuối sử dụng.

Chỉ có **mức B** mới đáp ứng đầy đủ yêu cầu “kiểm thử gói cài đặt trên máy đích”.

## 4. Dự án mẫu `PackageSmoke`

Ví dụ là một chương trình CLI Java SE, không yêu cầu Maven/Gradle. Nó thực hiện các kiểm tra có thể quan sát được:

- Đối số đầu vào phải chính xác là `smoke`.
- Resource `message.txt` phải được đọc từ **classpath bên trong JAR**.
- Java runtime đang chạy có feature version từ 17 trở lên.
- Thư mục `java.home` có tên `runtime` và có module file theo cấu trúc image trong ví dụ.
- Ứng dụng có quyền tạo, ghi, đọc và xóa **tệp tạm của user**, thay vì ghi vào thư mục cài đặt.

Cấu trúc source:

```text
package-smoke/
  src/
    demo/
      Main.java
  classes/           (sinh khi compile)
  input/
    app.jar          (sinh khi tạo JAR)
  out/
    image/
    installers/
```

### Tệp `src/demo/Main.java` hoàn chỉnh

```java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !"smoke".equals(args[0])) {
            throw new IllegalArgumentException("Expected argument: smoke");
        }

        String message;
        try (InputStream stream =
                Main.class.getResourceAsStream("/message.txt")) {
            if (stream == null) {
                throw new IllegalStateException("Missing bundled resource");
            }
            message = new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }

        Path runtime = Path.of(System.getProperty("java.home"))
                .toAbsolutePath().normalize();

        Path temp = Files.createTempFile("package-smoke-", ".txt");
        boolean tempIoOk;
        try {
            Files.writeString(temp, "ok", StandardCharsets.UTF_8);
            tempIoOk = "ok".equals(
                    Files.readString(temp, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(temp);
        }

        System.out.println("APP_ID=PackageSmoke");
        System.out.println("RESOURCE=" + message);
        System.out.println("ARG=" + args[0]);
        System.out.println("JAVA_17_PLUS=" +
                (Runtime.version().feature() >= 17));
        System.out.println("RUNTIME_DIR_NAME=" + runtime.getFileName());
        System.out.println("RUNTIME_MODULES=" + Files.isRegularFile(
                runtime.resolve("lib").resolve("modules")));
        System.out.println("TEMP_WRITE_READ=" + tempIoOk);
        System.out.println("SMOKE_RESULT=PASS");
    }
}
```

Chương trình không tự gọi `java` hoặc `javac` từ hệ thống khi đang chạy. `Main.class.getResourceAsStream("/message.txt")` là cách đọc resource từ classpath, không phụ thuộc vào đường dẫn `src` của máy build.

**Giới hạn:** `RUNTIME_DIR_NAME=runtime` và `RUNTIME_MODULES=true` là các dấu hiệu smoke test. Để xác minh chắc chắn runtime nằm trong ứng dụng đã cài, phải đối chiếu **đường dẫn tuyệt đối của `java.home`** với thư mục cài đặt trên máy đích. Hai dòng Boolean/tên thư mục không thay thế một cuộc kiểm tra đầy đủ về dependency.

## 5. Bước 1: biên dịch và tạo JAR trên Windows

Đặt `Main.java` ở đúng đường dẫn như trên. Mở **PowerShell** tại thư mục dự án rồi chạy:

```powershell
New-Item -ItemType Directory -Force -Path src\demo,classes,input,out\image,out\installers | Out-Null

javac --release 17 -encoding UTF-8 -d classes src\demo\Main.java
if ($LASTEXITCODE -ne 0) { throw "javac failed" }
```

Tạo `message.txt` dưới thư mục class output, dùng UTF-8 không BOM:

```powershell
[System.IO.File]::WriteAllText(
    (Join-Path (Resolve-Path classes).Path "message.txt"),
    "hello-from-package",
    (New-Object System.Text.UTF8Encoding($false))
)
```

Đóng JAR có manifest `Main-Class: demo.Main`:

```powershell
jar --create --file input\app.jar --main-class demo.Main -C classes .
if ($LASTEXITCODE -ne 0) { throw "jar failed" }

jar --list --file input\app.jar
java -jar input\app.jar smoke
if ($LASTEXITCODE -ne 0) { throw "JAR smoke test failed" }
```

`-C classes .` bao gồm **class và resource** trong JAR. Nếu chỉ tạo JAR từ file `.class` rồi bỏ `message.txt`, chương trình có thể chạy trong IDE nhưng không chạy khi đã phân phối.

Ở giai đoạn này `java -jar` **chưa chứng minh người dùng không cần Java riêng**, vì nó sử dụng runtime có sẵn trên build host. Mục tiêu của bước này là xác nhận JAR hợp lệ trước khi đóng gói native.

## 6. Bước 2: tạo và kiểm thử `app-image`

Trên Windows, tạo app-image bằng lệnh:

```powershell
jpackage --type app-image --name PackageSmoke --input input --main-jar app.jar --main-class demo.Main --app-version 1.0.0 --dest out\image --win-console
if ($LASTEXITCODE -ne 0) { throw "app-image creation failed" }
```

Giải thích:

| Option | Ý nghĩa |
| --- | --- |
| `--type app-image` | Chỉ tạo image, không tạo bộ cài |
| `--name PackageSmoke` | Tên ứng dụng và launcher |
| `--input input` | Thư mục chứa các file cần đóng vào ứng dụng |
| `--main-jar app.jar` | JAR chính tương đối với thư mục input |
| `--main-class demo.Main` | Entry point |
| `--app-version 1.0.0` | Metadata version |
| `--dest out\image` | Thư mục nhận image |
| `--win-console` | Tạo Windows console launcher, thích hợp demo CLI |

**`--win-console` chỉ dùng trên Windows**. Ứng dụng GUI có thể không cần console và nên dùng UI/log để xác minh.

Đường dẫn launcher của ví dụ:

```text
out\image\PackageSmoke\PackageSmoke.exe
```

Chạy launcher native:

```powershell
.\out\image\PackageSmoke\PackageSmoke.exe smoke
if ($LASTEXITCODE -ne 0) { throw "Image smoke failed" }
```

**Stdout chính xác đã kiểm chứng** từ image Windows tạo bằng OpenJDK 24 với mã `--release 17`:

```text
APP_ID=PackageSmoke
RESOURCE=hello-from-package
ARG=smoke
JAVA_17_PLUS=true
RUNTIME_DIR_NAME=runtime
RUNTIME_MODULES=true
TEMP_WRITE_READ=true
SMOKE_RESULT=PASS
```

Đây là tám dòng độc lập với đường dẫn máy build. Resource load thành công, tham số được truyền đúng, runtime có module file và test tệp temp hoạt động. **Không** kết luận từ tám dòng này rằng một installer MSI đã cài được hoặc mọi tính năng sản phẩm đều ổn.

### Khi image chạy được, còn cần thử gì?

Trong ứng dụng thực tế, hãy thử các chức năng phụ thuộc database/JDBC, HTTP, GUI/font, in ấn, file hệ thống, thư viện JNI và reflection. Một ứng dụng CLI nhỏ có thể chạy với runtime tối giản, nhưng ứng dụng GUI/enterprise có thể thiếu module hoặc native dependency mà smoke test đơn giản không phát hiện.

## 7. Bước 3: mô phỏng máy không có Java trên `PATH`

Để phát hiện việc launcher âm thầm gọi lệnh `java` của hệ thống, tạm bỏ Java khỏi `PATH` trong **một phiên PowerShell**, đồng thời bỏ `JAVA_HOME`. Lấy đường dẫn launcher tuyệt đối trước khi sửa môi trường:

```powershell
$launcher = (Resolve-Path .\out\image\PackageSmoke\PackageSmoke.exe).Path
$oldPath = $env:PATH
$oldJavaHome = $env:JAVA_HOME

try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:JAVA_HOME -ErrorAction SilentlyContinue

    Write-Output ("JAVA_ON_PATH=" +
        [bool](Get-Command java -ErrorAction SilentlyContinue))
    Write-Output ("JAVAC_ON_PATH=" +
        [bool](Get-Command javac -ErrorAction SilentlyContinue))
    Write-Output ("JAVA_HOME_SET=" + [bool]$env:JAVA_HOME)

    & $launcher smoke
    if ($LASTEXITCODE -ne 0) {
        throw "Native launcher failed without Java on PATH"
    }
}
finally {
    $env:PATH = $oldPath
    if ($null -eq $oldJavaHome) {
        Remove-Item Env:JAVA_HOME -ErrorAction SilentlyContinue
    } else {
        $env:JAVA_HOME = $oldJavaHome
    }
}
```

**Stdout thực tế đã kiểm chứng trong phép thử Windows:**

```text
JAVA_ON_PATH=False
JAVAC_ON_PATH=False
JAVA_HOME_SET=False
APP_ID=PackageSmoke
RESOURCE=hello-from-package
ARG=smoke
JAVA_17_PLUS=true
RUNTIME_DIR_NAME=runtime
RUNTIME_MODULES=true
TEMP_WRITE_READ=true
SMOKE_RESULT=PASS
```

Ba dòng đầu chứng minh `java`/`javac` không được tìm thấy từ `PATH` và `JAVA_HOME` không được thiết lập **trong shell thử nghiệm**. Tám dòng sau cho thấy launcher vẫn chạy đúng. Khối `finally` khôi phục môi trường, không gỡ JDK trên hệ thống.

**Cách báo cáo đúng:** “Smoke test không phụ thuộc Java/Javac trên PATH: PASS”. **Không** báo “đã chạy trên VM không cài Java” vì máy build vẫn có JDK trên đĩa, các file OS khác và native dependencies có thể giúp ứng dụng chạy.

## 8. Bước 4: tạo native installer từ image đã thử

### Windows: MSI hoặc EXE

Sau khi image đã PASS, dùng `jpackage --app-image` để tái sử dụng cây ứng dụng đã kiểm thử khi tạo installer. Trên Windows phải có **WiX tương thích với bản `jpackage`**. Tên công cụ tùy phiên bản có thể là `wix` hoặc `candle`/`light`; kiểm tra bản WiX và tài liệu đúng phiên bản JDK.

```powershell
jpackage --version
Get-Command wix,candle,light -ErrorAction SilentlyContinue
```

**Thông tin trung thực về phép thử của bài:** trên Windows/OpenJDK 24, cả ba lệnh `wix`, `candle`, `light` **không có trên `PATH`** khi kiểm tra. Vì vậy **chưa tạo MSI/EXE** và không tuyên bố “installer build PASS”. Bài cung cấp câu lệnh cần thực hiện trên máy build đã có WiX phù hợp:

```powershell
jpackage --type msi --name PackageSmoke --app-image out\image\PackageSmoke --app-version 1.0.0 --dest out\installers --win-menu --win-shortcut
if ($LASTEXITCODE -ne 0) { throw "MSI creation failed" }

Get-ChildItem .\out\installers -Filter *.msi
```

Đây là lệnh **hướng dẫn chưa được thực thi thành công ở môi trường thử hiện tại**, không phải một bản installer đã hoàn thành.

- `--type msi` chọn Windows MSI.
- `--app-image` dùng image đã tạo và smoke test.
- `--win-menu` và `--win-shortcut` yêu cầu Start Menu/Desktop shortcuts.
- `--app-version` là metadata version của sản phẩm.
- `--dest` chứa file MSI được tạo.

Muốn tạo EXE, dùng một **lượt build riêng** với `--type exe`, rồi kiểm tra file EXE và quy trình cài đặt của chính nó. Không coi EXE là đã PASS chỉ vì MSI build thành công.

**Chú ý về “installer có file”:** file `.msi` tồn tại sau khi build mới chỉ xác minh bước tạo gói. Cài đặt trên OS thật có thể thất bại bởi quyền, chính sách trust, phụ thuộc native, không tương thích OS/CPU hoặc cấu hình installer.

### Tại sao không tạo installer trực tiếp từ source/JAR rồi bỏ qua image?

`jpackage` hỗ trợ tạo installer trực tiếp từ application input, nhưng **quy trình image → smoke → installer** giúp cô lập lỗi:

1. Nếu JAR lỗi, sửa bước build Java.
2. Nếu image lỗi, sửa runtime/resource/launcher.
3. Nếu image chạy nhưng installer lỗi, tập trung vào toolchain/package/install.
4. Nếu installer cài được nhưng app lỗi trên target, tập trung vào môi trường đích, quyền, native dependency hoặc dữ liệu người dùng.

Dùng **`--app-image` của artifact đã smoke** giảm nguy cơ tạo installer từ file input khác với những gì vừa test, nhưng vẫn phải kiểm thử installer riêng.

## 9. Bước 5: kiểm thử trên máy đích không cài sẵn JDK

Dùng một **VM sạch hoặc host chuyên biệt** cùng OS/architecture mục tiêu. Nên có snapshot để tái tạo các thử nghiệm cài mới, gỡ và nâng cấp.

### Chuẩn bị máy đích

1. Ghi phiên bản OS, OS build, CPU architecture và tên user dùng test.
2. Xác minh chưa cài JDK/JRE hệ thống **theo tiêu chí môi trường test**. `Get-Command java` và `java -version` có thể không tìm thấy trên `PATH` nhưng **chưa đủ chứng minh** không có Java ở nơi khác; kiểm tra cả package/applications đã cài.
3. Không cài IDE, Maven/Gradle hay Java trước khi thử, tránh làm mờ dependency của installer.
4. Chuyển **installer được tạo thật** sang máy đích, không cần chuyển source code hay JDK.
5. Kiểm tra SHA-256 của file nhận được so với file build và xác minh chữ ký/publisher nếu release policy yêu cầu.
6. Kiểm tra quyền cài đặt cần thiết: user thường hay admin, install per-user hay per-machine.
7. Đảm bảo có cách thu thập installer log và application log để xử lý lỗi.

### Kiểm tra checksum

Trên máy build:

```powershell
Get-ChildItem .\out\installers -File | Get-FileHash -Algorithm SHA256
```

Trên máy đích, chạy `Get-FileHash -Algorithm SHA256` cho chính file nhận được và **đối chiếu** giá trị từ nguồn build đáng tin. Chỉ tính checksum riêng trên máy đích không tự chứng minh nguồn phát hành. SHA-256 phát hiện byte khác biệt; để xác thực publisher còn cần chữ ký số/kênh phân phối phù hợp.

### Cài gói

Với MSI trên VM Windows, mở file MSI bằng giao diện hoặc sử dụng `msiexec` và bật log. Ví dụ nếu file phát hành có đúng tên được tạo:

```powershell
msiexec /i ".\PackageSmoke-1.0.0.msi" /L*v ".\install.log"
```

Tên file đầu ra có thể phụ thuộc metadata và JDK; **đối chiếu tên thật bằng `Get-ChildItem` trước khi thực hiện**. Đây là câu lệnh minh họa dành cho VM sau khi bạn đã thực sự build MSI, **không phải lệnh đã chạy trong bài thử Windows trên build host**.

Cần xác nhận:

- Installer hiện đúng tên, phiên bản và publisher dự kiến.
- Có thông tin rõ ràng khi cần quyền administrator; không yêu cầu admin chỉ vì mã ứng dụng lưu dữ liệu sai vị trí.
- Installer thực sự cài launcher, JAR/resource và runtime.
- Shortcut/menu hoạt động nếu đã yêu cầu khi build.
- Hệ điều hành ghi nhận ứng dụng đã cài, file cài không bị thiếu.
- Ghi exit code và log lỗi thay vì chỉ xem thông báo “Finish”.

### Chạy ứng dụng **đã cài** trên máy đích

Mở launcher ở **thư mục sau cài đặt**, không chạy từ `out\image` trên máy build và không dùng `java -jar`. Với chương trình ví dụ, truyền `smoke` rồi so sánh 8 dòng ứng dụng với stdout ở bước 6.

Nếu app đã cài không mở console, dùng log/UI để xác minh, đặc biệt với GUI. Đường dẫn cài có thể khác nhau tùy MSI/EXE, quyền, kiểu cài và option `--install-dir`; **không giả định mọi máy đều dùng cùng `C:\Program Files\...`**.

Để xác minh runtime nhúng, có thể bổ sung vào mã hoặc log:

```java
System.out.println(Path.of(
        System.getProperty("java.home"))
        .toAbsolutePath().normalize());
```

Đây là **đoạn minh họa trong một phương thức đã import `Path`**, không nằm trong 8 dòng stdout cố định. Trên target, kiểm tra đường dẫn này nằm trong **cây ứng dụng đã cài**, không trỏ tới JDK/JRE khác trên host.

**Kết luận PASS mức B** chỉ khi VM/host đã được xác minh không có JDK/JRE hệ thống theo tiêu chí test, installer đã cài thành công và launcher/tính năng thực sự chạy từ nơi cài đặt.

## 10. Bước 6: kiểm thử quyền, dữ liệu, chức năng và trường hợp lỗi

Một ứng dụng Java thực tế không chỉ là chương trình `PackageSmoke` đơn giản. Sau khi xác minh launcher, chạy thêm các ca:

| Hạng mục | Kịch bản kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| **Tài nguyên** | Đọc icon, template, file config, font, dữ liệu đi kèm | Không phụ thuộc thư mục project/IDE |
| **Thư viện Java** | Dùng database driver, JSON parser, HTTP client | Không thiếu JAR/module ở runtime |
| **Thư viện native** | JNI, media codec, rendering, driver | Đúng OS/architecture, không `UnsatisfiedLinkError` |
| **Quyền** | Chạy bằng user không có quyền admin | Không ghi trái phép vào thư mục cài |
| **Đường dẫn** | Chạy từ working directory khác, path có space/Unicode | Không phụ thuộc đường dẫn tương đối sai |
| **Mạng** | Kết nối API/database theo cấu hình môi trường | Thông báo lỗi rõ khi thiếu mạng/credential |
| **Giao diện** | Mở cửa sổ bằng shortcut, kiểm tra DPI/font/theme | Không chỉ PASS vì process tồn tại |
| **Lỗi nhập liệu** | Đối số sai, file không tồn tại, quyền bị từ chối | Exit code/log có thể chẩn đoán |
| **Runtime** | So `java.home` với installed app, kiểm module | Không mượn JDK hệ thống |
| **Phiên bản** | Mở thông tin ứng dụng sau cài | App/JDK metadata đúng bản phát hành |

Một lỗi điển hình là chương trình ghi tệp ngay cạnh `.exe`, hoạt động trên máy build vì thư mục dự án được phép ghi nhưng lỗi trong `Program Files` khi chạy bằng user thường. **Dữ liệu người dùng** nên nằm trong thư mục user data hoặc temp thích hợp theo OS; không chỉnh sửa app payload/runtime của gói đã cài.

Ngoài ra, cố thử app khi **không có Maven/IDE trên target** và khi không có nguồn dữ liệu trong thư mục `src`. Nếu chỉ chạy được khi đặt working directory trùng project root, app chưa đạt mục tiêu phân phối độc lập.

## 11. Bước 7: nâng cấp và gỡ cài đặt

### Kiểm thử nâng cấp

Trên VM đã cài bản `1.0.0`, thử bản `1.0.1` được đóng gói theo cùng quy ước product identity/version, rồi kiểm tra:

- Installer nhận ra sản phẩm hiện có.
- Không tạo hai bản không mong muốn nếu thiết kế đòi thay thế bản cũ.
- Launcher sau nâng cấp đúng version và runtime.
- Dữ liệu người dùng được giữ, di chuyển hoặc xóa theo **chính sách đã công bố**.
- Shortcut, file association, service và quyền không bị hỏng.
- Lỗi giữa chừng có log và hướng xử lý/rollback phù hợp.

Windows `jpackage` cung cấp option `--win-upgrade-uuid`. Nếu dự án dùng, phải **giữ ổn định identity của quan hệ nâng cấp** trong các bản cần liên kết; không tạo UUID ngẫu nhiên mới cho mỗi release rồi kỳ vọng installer tự coi đó là cùng một sản phẩm. Bài demo 1.0.0 chỉ minh họa cài mới nên không tự sinh một identity giả.

### Kiểm thử gỡ

Dùng chức năng uninstall của OS/package manager rồi kiểm tra:

1. Installer/app biến mất khỏi danh sách chương trình theo mong đợi.
2. File payload, launcher, runtime và shortcut thuộc gói được dọn đúng.
3. Không để lại registry entry/service/file association mồ côi.
4. Không xóa dữ liệu người dùng ngoài chính sách.
5. Cài lại sạch sau khi gỡ vẫn chạy.
6. Log, exit code và snapshot VM xác nhận gỡ đã hoàn tất.

**Không suy luận “gỡ xong” chỉ vì xóa một thư mục**. Trên Windows MSI, OS vẫn quản lý product registration; trên Linux dùng package manager; trên macOS quy trình có thể khác giữa PKG và DMG.

Nếu ứng dụng có state/DB local quan trọng, kiểm tra migration và retention trước khi chấp nhận upgrade/uninstall PASS. Demo `PackageSmoke` không giữ dữ liệu lâu dài, nên không thể đại diện đầy đủ cho mọi ứng dụng.

## 12. Linux: tạo image, gói DEB/RPM và kiểm thử đúng OS

Trên Linux build host có JDK và toolchain tương ứng, sau khi có `input/app.jar`, có thể tạo app-image:

```bash
mkdir -p out/image out/installers
jpackage --type app-image \
  --name PackageSmoke \
  --input input \
  --main-jar app.jar \
  --main-class demo.Main \
  --app-version 1.0.0 \
  --dest out/image
```

Chạy launcher Linux:

```bash
./out/image/PackageSmoke/bin/PackageSmoke smoke
```

Tạo DEB từ chính image:

```bash
jpackage --type deb \
  --name PackageSmoke \
  --app-image out/image/PackageSmoke \
  --app-version 1.0.0 \
  --dest out/installers
```

Nếu dùng distro RPM, chọn `--type rpm` trên build host phù hợp và kiểm tra toolchain `rpm-build`. Ubuntu/Debian có thể yêu cầu `fakeroot` cho package build. Tên package/dependency thực tế cần được xác nhận từ file tạo ra.

Trên VM Linux đích, kiểm tra package metadata trước khi cài bằng package manager thích hợp; sau khi cài, chạy launcher trong **installed directory**, kiểm tra runtime và chức năng, rồi thử upgrade/uninstall. `command -v java`/`command -v javac` kiểm tra Java trên PATH nhưng không phải phép chứng minh duy nhất OS không cài runtime.

**Bản image Windows không chạy nguyên trên Linux.** JAR Java có thể dùng lại; native launcher và runtime image phải được tạo cho Linux. `glibc`, GUI toolkit, thư viện hệ thống, cấu hình sandbox/container và architecture có thể ảnh hưởng tính tương thích. Các lệnh Linux trong bài là **hướng dẫn**, chưa được thực thi trong lần thử Windows.

## 13. macOS: app bundle và PKG/DMG

Trên Mac build host có JDK thích hợp, tạo app-image bằng `jpackage`, **không dùng `--win-console`**:

```bash
mkdir -p out/image out/installers
jpackage --type app-image \
  --name PackageSmoke \
  --input input \
  --main-jar app.jar \
  --main-class demo.Main \
  --app-version 1.0.0 \
  --dest out/image
```

Một app-image macOS thường là `out/image/PackageSmoke.app`. Với app CLI, thử launcher từ Terminal:

```bash
./out/image/PackageSmoke.app/Contents/MacOS/PackageSmoke smoke
```

Tạo PKG từ app-image:

```bash
jpackage --type pkg \
  --name PackageSmoke \
  --app-image out/image/PackageSmoke.app \
  --app-version 1.0.0 \
  --dest out/installers
```

Đối với cách phát hành dùng DMG, chọn `--type dmg` và kiểm tra hành vi mở/copy ứng dụng theo thiết kế. **PKG khác DMG về cách người dùng cài**, vì vậy không được ghi PASS cho một định dạng dựa trên test của định dạng còn lại.

Khi phát hành macOS hiện đại, cần kiểm tra **signing, notarization, Gatekeeper, quarantine**, quyền app, user data và kiến trúc Apple Silicon/Intel theo phạm vi hỗ trợ. App mở được bằng Terminal chưa đủ chứng minh Finder/UI/distribution đã đúng.

Các lệnh macOS là **minh họa chưa thực thi** trong môi trường Windows của bài; phải chạy trên Mac phù hợp và có kết quả riêng.

## 14. Runtime image phải chứa đủ module và thư viện

Nếu không cung cấp `--runtime-image`, `jpackage` sử dụng `jlink` và các chính sách module của bản JDK đang dùng. Với JAR non-modular, cách chọn module khác ứng dụng modular; không suy luận mọi app chỉ cần `java.base` vì ví dụ CLI chạy được.

Kiểm tra các dependency tĩnh ban đầu:

```bash
jdeps --print-module-deps input/app.jar
```

**Giới hạn `jdeps`:** nó không phát hiện đủ mọi dependency phát sinh qua reflection, `ServiceLoader`, JNI hoặc các module chỉ được dùng trong một số cấu hình. Phải test chức năng thật.

Trên **JDK 25 trở lên**, Java packaging có thay đổi liên quan tới **service bindings**: image do `jpackage` tạo không còn mặc định tự gồm service bindings như một số bản trước. Ứng dụng dùng service provider phải kiểm tra đủ module và cân nhắc `--jlink-options --bind-services` theo tài liệu đúng version. Không dùng một runtime tối giản chưa test để phát hành production.

**Biên dịch `--release 17` không đồng nghĩa image mang Java 17.** Nếu chạy `jpackage` từ JDK 24, runtime mặc định trong image được lấy từ JDK 24. Kiểm tra phiên bản qua `Runtime.version()` và `java.home` trong app đã cài; ghi cả **JDK build**, **bytecode target** và **JDK runtime nhúng** trong release manifest.

Một số ứng dụng thật sự cần compiler (ví dụ IDE, build agent, `ToolProvider.getSystemJavaCompiler()`). Runtime do `jlink` tạo thường không có toàn bộ JDK tools, vì vậy với ứng dụng đó phải thiết kế đóng gói riêng phần compiler/tool hoặc thay đổi kiến trúc. “Không cần JDK hệ thống” chỉ đúng khi các chức năng ứng dụng đã được cung cấp đầy đủ trong gói.

## 15. QA theo từng giai đoạn: PASS khác NOT RUN

Để tránh báo cáo sai, tách từng mục:

| Hạng mục QA | Điều kiện PASS | Bằng chứng cần có |
| --- | --- | --- |
| Biên dịch | `javac --release 17` thành công | Exit code 0 và class output |
| Đóng JAR | Main class, resource và manifest đúng | `jar --list`, `java -jar` |
| App-image build | Launcher và runtime xuất hiện | `jpackage` exit code, cấu trúc thư mục |
| App-image smoke | Launcher chạy và in đủ kết quả | Stdout, exit code 0 |
| PATH simulation | Launcher chạy khi không thấy java/javac | Environment snapshot, stdout |
| Installer build | MSI/EXE/DEB/RPM/PKG/DMG thực sự tạo được | Build log, tệp package, checksum |
| Chuyển máy | Artifact trên VM giống bản build | SHA-256 hai đầu |
| Cài mới | OS installer cài đặt thành công | Install log và package inventory |
| Không JDK hệ thống | VM sạch vẫn chạy app đã cài | VM baseline và `java.home` |
| Tính năng | Resource, data path, OS/native dependency chạy đúng | Functional test |
| Nâng cấp | Upgrade đúng version/state | Test hai bản release |
| Gỡ cài đặt | File/shortcut/registry/service xử lý đúng policy | Uninstall log/snapshot |
| Trust/signing | Gói được chấp nhận theo policy phát hành | Chữ ký và OS security checks |

### Báo cáo kết quả đã xác minh của bài minh họa

```text
Application: PackageSmoke
Version: 1.0.0
Build host: Windows, OpenJDK 24
Compile target: javac --release 17
Java source/JAR: PASS
App-image build: PASS
App-image native launcher smoke: PASS
No-java/no-javac-on-PATH smoke: PASS
JAVA_HOME removed during smoke: PASS
WiX tools on PATH: NOT FOUND at test time
MSI/EXE installer build: NOT RUN
Install on actual clean target VM: NOT RUN
Upgrade/uninstall on target VM: NOT RUN
Linux/macOS package build and install: NOT RUN
```

**Không báo “installer target PASS”** chỉ vì app-image build và native launcher smoke thành công. Đó là hai bằng chứng khác nhau. Khi thực hiện bước VM, cập nhật đúng version OS, architecture, checksum, user, package name, log và exit code thật, rồi mới kết luận.

## 16. Các lỗi thường gặp khi làm bài thực hành

| Hiện tượng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `java -jar` chạy được nhưng launcher image không chạy | Sai Main-Class, thiếu resource/JAR, runtime/module | Kiểm tra jar manifest, input, jpackage options và launcher logs |
| Image chạy được nhưng MSI build lỗi | WiX thiếu hoặc không tương thích | Cài toolchain tương ứng, kiểm `jpackage --version` |
| Chỉ copy launcher sang VM rồi lỗi | Thiếu `app`/`runtime` | Chuyển **nguyên image** hoặc installer |
| Máy đích không có lệnh `java` | Đúng với môi trường không cài JDK | Chạy native launcher, không gọi `java -jar` |
| `ClassNotFoundException`, `NoClassDefFoundError` | Thiếu JAR/module/dependency nạp động | Kiểm tra artifact đầy đủ và chức năng thực |
| `UnsatisfiedLinkError` | JNI/OS library sai kiến trúc hoặc thiếu | Xác minh DLL/so/dylib và OS target |
| Installer cài thành công nhưng app không ghi file | Ghi vào thư mục install chỉ đọc | Dùng user data/temp directory |
| Shortcut không mở GUI | Working directory, quyền, missing config, signing | Mở từ đúng shortcut và xem application log |
| App mở nhưng không thấy stdout | GUI launcher không có console | Dùng UI/log, không mặc định lỗi |
| Nâng cấp tạo hai sản phẩm | Product identity/version khác policy | Kiểm tra upgrade identity, package metadata |
| Gỡ vẫn còn shortcut/service | Uninstaller không quản lý đủ payload | Kiểm tra package ownership/log |
| macOS chặn mở app | Gatekeeper/quarantine/signing/notarization | Xử lý signing/trust theo quy trình phát hành |
| Thử trên một OS rồi phát hành cho OS khác | Native launcher/runtime không tương thích | Build/test riêng từng OS/architecture |
| `--release 17` nhưng image mang runtime 24 | Bytecode target và runtime packaging khác nhau | Ghi runtime version thực, test trên image |

**Không sửa bằng cách yêu cầu người dùng cài JDK** để che lỗi đóng gói mà vẫn quảng bá ứng dụng không cần Java hệ thống. Tìm đúng dependency thiếu hoặc policy sai rồi cập nhật image.

## 17. Pipeline CI/CD nên tách thành các mốc rõ ràng

```text
Java source
    |
Compile + unit tests + package JAR
    |
    +-------------------+-------------------+
    |                   |                   |
Windows runner     Linux runner        macOS runner
    |                   |                   |
jpackage image     jpackage image      jpackage image
    |                   |                   |
Native smoke        Native smoke        Native smoke
    |                   |                   |
MSI/EXE build       DEB/RPM build        PKG/DMG build
    |                   |                   |
    +-------------------+-------------------+
                        |
            Clean VM / clean host QA
                        |
              Install + launch + logs
                        |
            Upgrade + uninstall checks
                        |
           Sign/distribute as required
```

Thứ tự signing/notarization và package build có thể khác nhau giữa OS, nên pipeline phải tuân theo hướng dẫn của chính nền tảng. Không sửa file trong app bundle đã ký rồi kỳ vọng chữ ký còn hợp lệ.

Trong mỗi job, ghi version JDK, bản OS, CPU architecture, artifact checksum, option jpackage, kết quả smoke và log. Với Windows CLI dùng `--win-console`; với GUI, dùng ứng dụng hoặc API log phù hợp. Một image chạy trên laptop developer không thay thế kiểm thử clean VM.

Ngoài công việc cài đặt, cần có chiến lược **cập nhật JVM nhúng**. App-image chứa runtime riêng nên cập nhật Java ở hệ thống người dùng **không đảm bảo tự vá** runtime này. Nhà phát hành phải rebuild và phân phối ứng dụng khi có bản vá JDK cần thiết.

## 18. Bài tập củng cố

**Câu 1.** App-image tạo thành công và chạy được trên Windows build host. Có thể kết luận MSI cài tốt trên VM sạch chưa?

**Đáp án:** Chưa. Chỉ có bằng chứng image/launcher, chưa có bằng chứng installer build và install. Phải tạo MSI thực tế rồi cài/chạy/gỡ trên VM đích.

**Câu 2.** Khi bỏ `java`/`javac` khỏi `PATH` và bỏ `JAVA_HOME`, launcher vẫn in `SMOKE_RESULT=PASS`. Điều đó chứng minh gì?

**Đáp án:** Launcher không phụ thuộc các lệnh Java đó trong **phiên shell đang thử**. Máy build vẫn có JDK trên đĩa, nên chưa chứng minh máy sạch không cài Java.

**Câu 3.** Vì sao cần đưa `message.txt` vào JAR thay vì đọc ở `src/demo`?

**Đáp án:** Máy người dùng không có project source. Resource phải nằm trong artifact và được load qua classpath.

**Câu 4.** Compile với `--release 17` và đóng gói bằng JDK 24 thì runtime nhúng chắc chắn là 17 không?

**Đáp án:** Không. Khi `jpackage` tự tạo runtime, nó thường lấy từ JDK dùng để đóng gói. `--release` chỉ ràng buộc bytecode/API lúc compile.

**Câu 5.** Vì sao app có JVM nhúng vẫn có thể bị `UnsatisfiedLinkError` trên máy đích?

**Đáp án:** Runtime Java không tự chứa mọi thư viện native, driver hoặc dependency OS của ứng dụng. Cần đóng gói/test theo OS và kiến trúc tương ứng.

**Câu 6.** Nếu uninstall đã xóa `.exe` nhưng product vẫn hiển thị trong danh sách cài đặt, có thể coi PASS không?

**Đáp án:** Không. Phải kiểm tra hành vi uninstall của package manager, registry/service/shortcut và chính sách dữ liệu người dùng, không chỉ một file.

**Câu 7.** Có thể dùng `jpackage --type msi` trên Linux để tạo MSI Windows trực tiếp không?

**Đáp án:** Không theo hỗ trợ native của công cụ: mỗi định dạng phải được tạo trên nền tảng tương ứng. Có thể dùng lại mã Java/JAR và build trên Windows runner.

**Câu 8.** Vì sao checksum bằng nhau chưa thay chữ ký của nhà phát hành?

**Đáp án:** SHA-256 giúp so sánh byte nếu giá trị tham chiếu đáng tin cậy, nhưng không tự xác thực ai đã tạo file. Quy trình phân phối công khai cần chính sách signing/trust riêng.

## 19. Checklist cuối cùng

**Đầu vào:** JDK phù hợp, JAR có class/manifest/resource, dependency khai báo rõ, version và OS/arch mục tiêu xác định.

**Image:** `jpackage --type app-image` thành công; launcher/runtime hiện diện; chạy native launcher; so sánh stdout và exit code; thử shell không có Java/Javac trên PATH.

**Installer:** công cụ native packaging có sẵn; tạo đúng `msi`/`exe`/`deb`/`rpm`/`pkg`/`dmg`; kiểm metadata, checksum, signing policy, filename và build logs.

**Target VM:** đúng OS/CPU; không cài JDK/JRE riêng; cài installer, chạy launcher **đã cài**, xác minh runtime nhúng và mọi chức năng quan trọng; thử tài khoản user thường và đường dẫn dữ liệu.

**Vòng đời:** chạy quy trình upgrade/uninstall, kiểm sạch package-owned files và dữ liệu người dùng theo chính sách; lưu bằng chứng/test report riêng cho từng nền tảng.

**Kết luận:** Quy trình có thể kiểm chứng là **Java source → JAR → app-image → native installer → cài, chạy, nâng cấp và gỡ trên máy đích sạch**. `jpackage` giải quyết việc mang runtime Java theo ứng dụng, nhưng không tự bảo đảm tất cả OS dependencies, quyền, việc cài đặt hay trải nghiệm người dùng. Chỉ ghi **PASS** cho những bước đã thực sự chạy và đã có bằng chứng.

### Tài liệu tham khảo còn áp dụng

- [JEP 392 — Packaging Tool, chính thức từ JDK 16](https://openjdk.org/jeps/392).
- [Oracle JDK 25 — Packaging Overview: OS prerequisites, app-image, runtime](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html).
- [Oracle JDK 25 — jpackage Command (MSI, EXE, DEB, RPM, DMG, PKG)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html).
- [Oracle JDK 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html).
- [Oracle JDK 21 — jpackage Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html).
- [Java SE 21 — Files API cho việc kiểm thử resource và tệp](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).
