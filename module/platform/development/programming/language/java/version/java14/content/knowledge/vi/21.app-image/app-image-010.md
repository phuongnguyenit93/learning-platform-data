# Chạy thử app-image trên máy không cài sẵn JDK

## 1. Mục tiêu của bài kiểm thử

Máy phát triển thường có `java`, `javac`, `jar`, `jpackage`, biến môi trường `JAVA_HOME` và nhiều thư viện ngoài. Vì vậy việc `java -jar app.jar` chạy được trên máy đó **không chứng minh** sản phẩm có thể chạy trên máy của người dùng chưa cài Java.

Với **app-image** được tạo bằng `jpackage --type app-image`, mục tiêu là phân phối ứng dụng cùng một **native launcher** và **Java runtime image** phù hợp. Người dùng khởi động launcher của hệ điều hành mà không phải tự cài JDK hay JRE. Tuy nhiên cần phân biệt hai mức xác minh:

1. **Smoke test trên máy build, tạm ẩn Java khỏi `PATH` và bỏ `JAVA_HOME`:** chứng minh launcher không phụ thuộc vào lệnh `java` hệ thống trong môi trường đang thử. Cách này có thể tự động hóa nhưng **không biến máy build thành máy sạch thực sự**.
2. **Test trên máy ảo hoặc máy vật lý sạch, không cài JDK/JRE:** chuyển nguyên app-image sang đó, khởi động launcher, kiểm tra runtime đi kèm và chức năng ứng dụng. Đây là bước xác nhận cuối cho yêu cầu của bài.

**Điểm cốt lõi:** `app-image` có thể mang Java runtime đi kèm; nó **không phải JAR thuần**, **không phải bộ cài hệ điều hành**, và **không tự tương thích mọi OS/CPU**.

**Phiên bản còn áp dụng:** `jpackage` từng là công cụ incubating khi xuất hiện trong Java 14, nhưng trở thành công cụ chuẩn từ **JDK 16** (JEP 392). Bài dùng cú pháp ổn định của JDK **17+**, không hướng dẫn gọi module incubator hay dùng lệnh legacy.

## 2. Vì sao app-image không cần JDK hệ thống?

`jpackage` tạo image gồm các thành phần hỗ trợ nhau:

```text
Windows (khái quát):
CleanLaunch/
  CleanLaunch.exe     <- native launcher
  app/                <- JAR và launcher configuration
  runtime/            <- Java runtime image đi kèm

Linux (khái quát):
CleanLaunch/
  bin/                <- launcher
  lib/
    app/              <- JAR và tài nguyên
    runtime/          <- Java runtime image

macOS (khái quát):
CleanLaunch.app/
  Contents/
    MacOS/            <- launcher
    app/              <- JAR/tài nguyên
    runtime/          <- Java runtime image
```

Chi tiết nội bộ có thể thay đổi theo JDK/OS; đây là sơ đồ hướng dẫn, không phải cam kết về mọi file. Nếu không cung cấp `--runtime-image` riêng, `jpackage` thường dùng `jlink` để tạo runtime từ JDK đang chạy công cụ. Runtime đó chứa JVM và các module Java cần thiết theo chiến lược tạo image.

**Không copy riêng `CleanLaunch.exe` hoặc chỉ file `.jar`**. Launcher phụ thuộc vào cây thư mục ứng dụng, runtime và các file đi kèm. Nếu tạo file ZIP để chuyển máy, hãy nén/copy **toàn bộ app-image** và giải nén giữ nguyên cấu trúc.

Phân biệt sản phẩm:

| Sản phẩm | Thành phần chính | Cách khởi động trên máy sạch |
| --- | --- | --- |
| `app.jar` | Bytecode và tài nguyên Java | Thường cần `java -jar app.jar` từ một Java runtime đã có |
| `app-image` | Launcher native + JAR/modules + runtime | Chạy launcher native của app-image; không cần lệnh `java` hệ thống |
| `native installer` | Gói cài đặt theo OS, thường cài cả app-image/runtime | Chạy trình cài đặt rồi mở ứng dụng |

`app-image` có thể dùng để chạy trực tiếp hoặc làm đầu vào cho bước tạo installer. Kiểm thử `app-image` **không thay** kiểm thử install/upgrade/uninstall nếu sản phẩm cuối cùng là installer.

## 3. Điều kiện tiên quyết và ranh giới nền tảng

Máy **build** cần JDK có `javac`, `jar` và `jpackage`. Máy **chạy** chỉ cần OS và phần mềm hệ thống phù hợp với app-image đã tạo; JVM đã nằm trong image.

| Yếu tố | Yêu cầu trên máy build | Yêu cầu trên máy thử |
| --- | --- | --- |
| JDK | Cần để compile và đóng gói | Không cần cài riêng nếu runtime đã đi kèm |
| OS | Chạy `jpackage` trên đúng OS mục tiêu | Cùng họ OS với image đã build |
| CPU | JDK/runtime và native library đúng kiến trúc | Kiến trúc có thể thực thi image đó |
| Java runtime | `jpackage` tạo hoặc nhận `--runtime-image` | Có trong toàn bộ app-image |
| Thư viện ngoài Java | Được build/copy phù hợp OS | Native dependency của OS/app phải có |
| Tài nguyên | Đưa vào JAR/app-image | Phải load được sau khi chuyển sang máy sạch |

**Không có cross-platform packaging trực tiếp**: Windows image không thể chuyển nguyên vẹn sang Linux/macOS để chạy. Nếu phát hành Windows x64, Linux x64 và macOS ARM64, phải tạo và test những image tương ứng trên môi trường đóng gói hỗ trợ.

Trên máy build, dùng:

```bash
java -version
javac -version
jpackage --version
jpackage --help
```

Kết quả `jpackage --help` phụ thuộc OS/JDK; nó cho biết các loại package và option hiện có, chẳng hạn `--win-console` chỉ áp dụng trên Windows. Không cần gói `msi`/`dmg` để kiểm chứng riêng một `app-image`.

## 4. Chương trình thử nghiệm Java 17+ có resource

Ví dụ này dùng **Windows và PowerShell**. Ứng dụng có một file resource trong JAR, nhận một tham số dòng lệnh và xác minh JVM đang chạy bên trong cấu trúc runtime của image.

**Tệp `src/demo/Main.java`:**

```java
package demo;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public class Main {
    public static void main(String[] args) throws Exception {
        String message;
        try (InputStream input = Objects.requireNonNull(
                Main.class.getResourceAsStream("/message.txt"),
                "message.txt")) {
            message = new String(input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }

        Path javaHome = Path.of(System.getProperty("java.home"))
                .toAbsolutePath().normalize();
        System.out.println("MESSAGE=" + message);
        System.out.println("ARGS=" + String.join(",", args));
        System.out.println("RUNTIME_INSIDE_IMAGE=" +
                (javaHome.toString().contains("CleanLaunch")
                        && javaHome.endsWith("runtime")));
        System.out.println("MODULES_PRESENT=" +
                Files.isRegularFile(javaHome.resolve("lib")
                        .resolve("modules")));
        System.out.println("JAVA_17_PLUS=" +
                (Runtime.version().feature() >= 17));
    }
}
```

Tạo thêm resource **`classes/message.txt`** chứa văn bản:

```text
hello-from-resource
```

Các chỉ số được chọn có mục đích:

- `MESSAGE`: kiểm tra resource đã được đưa vào JAR và load qua classpath; không dựa vào đường dẫn mã nguồn của IDE.
- `ARGS`: kiểm tra launcher chuyển đối số `smoke` tới `main(String[])`.
- `RUNTIME_INSIDE_IMAGE`: kiểm tra **đặc thù image tên `CleanLaunch` trong ví dụ Windows**, không phải một API về tên thư mục của mọi ứng dụng.
- `MODULES_PRESENT`: kiểm tra file module Java có trong runtime được khởi chạy.
- `JAVA_17_PLUS`: kiểm tra runtime thực tế có feature version từ 17 trở lên.

Mã trên **không** dùng lệnh shell `java` hoặc `javac` khi chạy, và không cần thư viện ngoài Java SE.

## 5. Biên dịch và tạo app-image

Tại thư mục dự án có tệp `src/demo/Main.java`, chạy PowerShell:

```powershell
New-Item -ItemType Directory -Force classes, input, out | Out-Null

javac --release 17 -encoding UTF-8 -d classes src/demo/Main.java

[System.IO.File]::WriteAllText(
    (Join-Path (Resolve-Path classes).Path "message.txt"),
    "hello-from-resource",
    (New-Object System.Text.UTF8Encoding($false))
)

jar --create --file input/demo.jar --main-class demo.Main -C classes .

jpackage --type app-image --name CleanLaunch --input input --main-jar demo.jar --main-class demo.Main --app-version 1.0 --dest out --win-console
```

**Lưu ý:** `--win-console` dùng để thấy stdout của ứng dụng dòng lệnh trong Windows; không áp dụng cho macOS/Linux. Ở bước tạo JAR, `-C classes .` sẽ đóng cả class đã biên dịch và `message.txt` trong thư mục `classes`.

Nên kiểm tra `$LASTEXITCODE` sau `javac`, `jar` và `jpackage` trong CI; PowerShell không mặc định dừng toàn bộ script khi một chương trình native thất bại. Nếu file image cũ đã tồn tại, dùng output mới ở thư mục build sạch thay vì tự ghi đè không kiểm soát.

Với JDK và toolchain Windows thích hợp, kết quả là:

```text
out/
  CleanLaunch/
    CleanLaunch.exe
    app/
    runtime/
```

Không cần WiX để tạo `--type app-image` theo nhu cầu thử nghiệm này; các công cụ tạo `msi`/`exe` installer là bước khác. Nếu ứng dụng thật dùng dependency ngoài, bảo đảm JAR/thư viện/resource đó được cung cấp đúng cho `jpackage`, không chỉ có trên máy build.

### Thử trên máy build trước khi ẩn Java

```powershell
.\out\CleanLaunch\CleanLaunch.exe smoke
```

Kết quả mong đợi của chương trình là:

```text
MESSAGE=hello-from-resource
ARGS=smoke
RUNTIME_INSIDE_IMAGE=true
MODULES_PRESENT=true
JAVA_17_PLUS=true
```

Nếu `java.home` thực tế không nằm trong `CleanLaunch\runtime`, hãy kiểm tra lại cấu trúc image và cách khởi chạy. Không coi `PATH` có JDK là bằng chứng launcher đã dùng JDK hệ thống; cần nhìn runtime thực sự đang thực thi.

## 6. Cấp A — kiểm thử khi không có lệnh Java trên PATH

Đoạn PowerShell sau tạm thời thu hẹp `PATH` trong **phiên shell hiện tại** và xóa `JAVA_HOME` **trong phạm vi thử nghiệm**. Nó không gỡ JDK, không chỉnh Environment Variables toàn hệ thống và có khối `finally` để khôi phục thiết lập ban đầu.

Lấy đường dẫn tuyệt đối tới launcher **trước** khi thay `PATH`:

```powershell
$launcher = (Resolve-Path .\out\CleanLaunch\CleanLaunch.exe).Path
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
        throw "Packaged launcher failed with exit code $LASTEXITCODE"
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

**Stdout đã kiểm chứng** khi build image trên Windows với JDK 24 và biên dịch mã nguồn bằng `--release 17`:

```text
JAVA_ON_PATH=False
JAVAC_ON_PATH=False
JAVA_HOME_SET=False
MESSAGE=hello-from-resource
ARGS=smoke
RUNTIME_INSIDE_IMAGE=true
MODULES_PRESENT=true
JAVA_17_PLUS=true
```

Đọc đúng ý nghĩa:

1. Ba dòng đầu chứng minh trong phiên thử này không có lệnh `java`/`javac` được tìm qua `PATH` và không còn biến `JAVA_HOME`.
2. Năm dòng tiếp theo xác nhận **launcher của image vẫn chạy thành công**, đọc resource, nhận tham số và dùng runtime của image.
3. Điều đó **không chứng minh JDK bị gỡ khỏi ổ đĩa**: đây là kiểm thử **độc lập với Java trên PATH**, không phải kiểm thử máy sạch tuyệt đối.
4. `RUNTIME_INSIDE_IMAGE=true` được viết theo cấu trúc file của ví dụ; khi đổi tên ứng dụng hoặc OS phải thay cách xác minh đường dẫn.

**Không xóa/cài lại JDK hệ thống để thực hiện smoke test.** Sử dụng môi trường subprocess/shell có phạm vi rõ ràng như ví dụ là đủ cho cấp A.

## 7. Cấp B — thử trên VM hoặc máy không cài Java thật sự

Để đáp ứng chính xác tiêu chí “**máy không cài sẵn JDK**”, phải có một môi trường chạy độc lập với máy build:

1. **Chuẩn bị VM sạch** với bản Windows và CPU architecture nằm trong phạm vi hỗ trợ của ứng dụng. Ghi phiên bản OS, OS build và kiến trúc.
2. **Kiểm tra trạng thái Java của máy đó.** Xác minh không cài sẵn JDK/JRE hệ thống; `java -version` và `javac -version` không được tìm thấy trên `PATH` chỉ là một phép kiểm tra, chưa phải chứng minh duy nhất.
3. **Chuyển nguyên thư mục `out\CleanLaunch`** bằng ZIP, file share hoặc artifact CI. Khi giải nén, giữ nguyên `CleanLaunch.exe`, `app`, `runtime` và các file phụ.
4. **Khởi chạy launcher native:** từ terminal PowerShell bên máy thử, đứng ở thư mục chứa `CleanLaunch` rồi chạy `.\CleanLaunch\CleanLaunch.exe smoke`.
5. **Xác minh môi trường runtime:** khi dùng ví dụ, kiểm tra `MESSAGE`, `ARGS`, `RUNTIME_INSIDE_IMAGE`, `MODULES_PRESENT` và `JAVA_17_PLUS`; với app thực tế còn phải xác nhận `java.home` thuộc image, không phải một JDK trên máy.
6. **Kiểm tra các chức năng thật:** mở màn hình, đọc/ghi dữ liệu, xử lý tệp, gọi API, in ấn, JDBC, UI/font, native library, network và các chức năng liên quan nếu có.
7. **Thử cả điều kiện lỗi:** không có quyền ghi trong thư mục cài ứng dụng, thư mục người dùng khác, đường dẫn chứa khoảng trắng, môi trường không có IDE, thư viện ngoài hoặc mạng bị giới hạn theo tình huống.
8. **Ghi kết quả và snapshot VM:** lưu phiên bản app, JDK đã dùng để đóng gói, OS/CPU, stdout/stderr, exit code, log và cách tái hiện mọi lỗi.
9. **Lặp lại trên các môi trường được hỗ trợ:** một bản Windows sạch không thay thế mọi Windows hoặc bản Linux/macOS. Có thể chọn ma trận đại diện theo chính sách hỗ trợ.

**Lệnh mẫu tại máy Windows sạch** (giả sử thư mục `CleanLaunch` đã được chuyển sang):

```powershell
.\CleanLaunch\CleanLaunch.exe smoke
$LASTEXITCODE
```

Launcher ứng dụng GUI có thể không có console. Khi ấy cần kiểm tra giao diện và log thay vì dựa duy nhất vào stdout.

**Giới hạn thực tế được nói rõ:** phép kiểm thử chạy trong bài đã thực hiện thành công **cấp A** trên máy có JDK và đã ẩn `java`/`javac` khỏi `PATH`. **Chưa thực hiện cấp B trên máy/VM sạch thật sự** trong ví dụ; không được dùng kết quả cấp A để tuyên bố đã xác nhận hoàn toàn cấp B.

## 8. Kiểm thử trên Linux và macOS

Nguyên lý vẫn giống nhau: đóng gói trên **đúng OS/CPU** rồi chạy launcher trên máy sạch đúng nền tảng.

### Linux

Trên máy build Linux có JDK, sau khi tạo `input/demo.jar`:

```bash
jpackage --type app-image --name CleanLaunch \
  --input input --main-jar demo.jar --main-class demo.Main \
  --app-version 1.0 --dest out
```

Cấu trúc image Linux thường đặt launcher ở:

```bash
./out/CleanLaunch/bin/CleanLaunch smoke
```

Lệnh Linux được nêu để hướng dẫn, **chưa được thực thi trong phép kiểm thử Windows**. Trên VM Linux sạch, dùng `command -v java`/`command -v javac` để kiểm tra lệnh hệ thống, chạy launcher và xác nhận runtime được dùng nằm trong image. Còn phải xác minh các thư viện native như `glibc` và những dependency mà ứng dụng yêu cầu.

### macOS

Trên máy build macOS, tạo image bằng `jpackage --type app-image` tương tự. Launcher thường có vị trí:

```bash
./out/CleanLaunch.app/Contents/MacOS/CleanLaunch smoke
```

Với ứng dụng có GUI, kiểm tra cả việc mở qua Finder. Code signing, notarization, quarantine và Gatekeeper có thể ảnh hưởng việc mở ứng dụng sau khi tải xuống; điều đó **khác** câu hỏi “JDK hệ thống có cần được cài không?”. Kiểm tra thêm kiến trúc Intel/Apple Silicon tương ứng.

**Lưu ý:** Không chuyển nguyên Windows image sang Linux/macOS. Java bytecode có thể tái sử dụng, nhưng native launcher và runtime image đã được tạo theo nền tảng gốc.

## 9. Kiểm tra runtime thực tế: đừng nhầm `--release` với runtime nhúng

Trong ví dụ, mã được biên dịch với:

```bash
javac --release 17 ...
```

Nhưng `jpackage` được chạy bằng **JDK 24**. Do đó ứng dụng có thể chạy trên runtime Java 24 và vẫn in `JAVA_17_PLUS=true`. Điều đó là đúng vì `--release 17` chỉ hạn chế API và bytecode ở bước biên dịch.

Muốn biết runtime được dùng thật sự:

```java
String home = System.getProperty("java.home");
int feature = Runtime.version().feature();
System.out.println(home);
System.out.println(feature);
```

Đây là đoạn code để đặt trong phương thức, không phải chương trình độc lập. Với `app-image`, `java.home` phải hướng vào runtime đi kèm. Nếu bạn cần **phiên bản runtime cố định**, dùng đúng JDK cho bước đóng gói hoặc cung cấp một runtime đã tạo bằng `jlink`:

```bash
jpackage --type app-image --name CleanLaunch \
  --input input --main-jar demo.jar --main-class demo.Main \
  --runtime-image path/to/runtime-image --dest out
```

Đây chỉ là **mẫu lệnh**, vì `path/to/runtime-image` phải được thay bằng runtime thực tế. Runtime đó phải đúng OS/CPU, Java version và đầy đủ module. Dùng runtime tùy chỉnh bị thiếu `java.sql`, `java.desktop` hoặc module khác có thể khiến chức năng ứng dụng lỗi trên máy sạch, dù màn hình khởi động chạy tốt.

Có thể phân tích dependency tĩnh ban đầu bằng:

```bash
jdeps --print-module-deps input/demo.jar
```

Tuy nhiên, `jdeps` không tự phát hiện mọi dependency được nạp động qua reflection, service provider hoặc JNI. Kiểm thử **chức năng thật** vẫn là bước bắt buộc.

**Lưu ý hiện hành:** từ JDK 25, runtime do `jpackage` tạo không còn tự động thêm service bindings giống một số phiên bản trước. Với ứng dụng dùng `ServiceLoader`, kiểm tra module provider trong runtime; khi cần có thể cấu hình `--jlink-options --bind-services` theo tài liệu JDK tương ứng.

## 10. Những lỗi thường gặp trên máy không có JDK

| Hiện tượng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ có launcher, app không mở | Copy thiếu thư mục `runtime`/`app` | Phân phối **toàn bộ** app-image |
| `java -jar` không chạy trên VM sạch | Máy không có lệnh `java`/JRE | Chạy native launcher của image |
| `NoClassDefFoundError` hoặc `ClassNotFoundException` | Thiếu JAR/dependency/module trong runtime | Kiểm tra `--input`, JAR, `jlink` và module cần dùng |
| `UnsatisfiedLinkError` | DLL/`.so`/`.dylib` không tương thích hoặc không có | Đóng gói native library đúng OS/CPU |
| Mất config/template | Mã dựa vào thư mục của IDE, file chưa vào JAR | Đọc tài nguyên qua classpath/path được thiết kế |
| Không ghi được dữ liệu | Thư mục image/cài đặt không có quyền ghi | Dùng user data directory phù hợp OS |
| App gọi lệnh `java` trong subprocess rồi lỗi | Logic yêu cầu Java từ `PATH` thay vì dùng runtime nhúng | Thiết kế lại subprocess hoặc dùng đường dẫn runtime đúng |
| App cần `javac` nhưng runtime không có | Ứng dụng thật sự là công cụ biên dịch | Cần đóng gói compiler/tool hoặc đổi thiết kế |
| GUI không hiện stdout | Windows launcher không mở console | Dùng `--win-console` cho CLI, với GUI kiểm tra log/UI |
| Chạy được trên máy dev, không được trên VM | Thiếu dependency OS, native lib, network, font, credential | Rà soát environment và test theo tính năng |
| Launcher lỗi trên ARM64 | Image tạo cho kiến trúc không tương thích | Build/test riêng cho đúng kiến trúc |

### Khi ứng dụng thực sự cần JDK

Phần lớn ứng dụng Java chỉ cần Java runtime, nhưng **không phải tất cả**. Một IDE, compiler service, build tool hoặc sản phẩm gọi `javax.tools.ToolProvider.getSystemJavaCompiler()` có thể cần module/compiler hoặc công cụ JDK. Runtime tối giản do `jlink` tạo có thể không chứa các thành phần ấy.

Vì vậy cần phân biệt “**ứng dụng Java thông thường chạy không cần JDK cài riêng**” với “**ứng dụng không cần bất kỳ chức năng compiler nào**”. Đối với sản phẩm thật sự phải biên dịch mã, hãy đóng gói module/tool cần thiết hoặc thay đổi yêu cầu sản phẩm — đừng bắt người dùng cài JDK rồi tuyên bố image đã tự đủ.

## 11. Kế hoạch QA trước khi phát hành

| Tiêu chí | Kết quả cần xác minh |
| --- | --- |
| Build JAR | Main class, resource và dependency đầy đủ |
| Tạo image | `jpackage --type app-image` thành công trên OS/CPU đích |
| Launcher | File launcher native tồn tại và chạy được |
| Runtime | `java.home` trỏ vào image, các module cần dùng có mặt |
| Không phụ thuộc Java trên PATH | `java`/`javac` vắng ở `PATH`, launcher vẫn chạy |
| Máy sạch thực tế | Chạy được trên VM/host không cài JDK/JRE hệ thống |
| Tham số và tài nguyên | Load resource, nhận argument, xử lý dữ liệu chính xác |
| Tính năng nghiệp vụ | Các kịch bản chính và lỗi dự kiến đều được kiểm tra |
| Thư viện native | Có đủ DLL/so/dylib và hệ thống tương thích |
| Quyền | Không đòi quyền administrator không cần thiết |
| Phát hành installer | Nếu có, test install/upgrade/uninstall riêng |
| Log và version | Có khả năng truy vết môi trường, lỗi và version runtime |

Bên cạnh chức năng cơ bản, nên chạy lại sau khi chuyển image tới **thư mục khác**, đổi working directory, đăng nhập bằng user thường, dùng đường dẫn có khoảng trắng hoặc Unicode và thử các phiên bản hệ điều hành trong phạm vi hỗ trợ.

Không báo `PASS cấp B` chỉ vì cấp A thành công, cũng không coi một lần mở được màn hình splash là bằng chứng toàn bộ ứng dụng hoạt động ổn.

## 12. CI/CD: kiểm tra không dùng Java hệ thống ở đâu?

Với ứng dụng đa nền tảng, có thể build/test JAR chung, nhưng tạo app-image **riêng trên mỗi runner**:

```text
Java source -> JAR/tests
                  |
          +-------+-------+
          |       |       |
       Windows  Linux   macOS
        runner  runner  runner
          |       |       |
       jpackage app-image
          |       |       |
       Smoke native launcher
       without Java on PATH
          |       |       |
       Clean VM/host testing
          |       |       |
         Release artifacts
```

**Không cố build một Windows image rồi phát hành nó như Linux image.** Nếu hỗ trợ cả x64 và ARM64, cần kiểm soát runtime và các thư viện native tương ứng. Sau khi đã xác nhận image hoạt động, nếu tạo native installer, hãy bổ sung job test **cài đặt, nâng cấp, gỡ**.

Trong CI cần lưu thông tin: mã commit, version app, JDK dùng để `jpackage`, OS/CPU runner, lệnh build, checksum artifact, kết quả launch và log. Mật khẩu, token, khóa signing và cấu hình riêng không được đóng trong image hoặc log công khai.

## 13. Tự kiểm tra

**Câu 1.** Vì sao `java -jar app.jar` chạy trên laptop dev không đủ để xác nhận app-image tự đủ?

**Đáp án:** Lệnh đó dùng runtime hệ thống trên laptop; chưa chạy native launcher, chưa chứng minh runtime/dependency nằm trong image.

**Câu 2.** Sau khi tạm ẩn `java` và `javac` khỏi `PATH`, launcher chạy tốt. Đã thỏa yêu cầu “máy không cài sẵn JDK” chưa?

**Đáp án:** Chưa hoàn toàn. Đây là **PASS cấp A**. Cần thử trên máy/VM thực sự không cài Java để kết luận **PASS cấp B**.

**Câu 3.** Khi chuyển ứng dụng sang VM, có thể chỉ copy `CleanLaunch.exe` không?

**Đáp án:** Không. Phải copy toàn bộ cây app-image, gồm runtime và các file ứng dụng.

**Câu 4.** Vì sao `javac --release 17` và `Runtime.version().feature() == 24` có thể cùng đúng?

**Đáp án:** `--release` điều khiển bytecode/API lúc compile; image có thể được tạo từ JDK 24, nên runtime thực tế là 24.

**Câu 5.** App không cần JDK hệ thống nhưng vẫn gặp `UnsatisfiedLinkError`. Có mâu thuẫn không?

**Đáp án:** Không. Runtime Java đi kèm không bảo đảm đủ mọi thư viện native hoặc dependency OS của ứng dụng.

**Câu 6.** Vì sao cần kiểm tra một chức năng đọc resource trong image?

**Đáp án:** Vì trong IDE resource có thể nằm ở thư mục source mà chưa được đóng vào JAR; image tự đủ phải load được từ artifact đã phân phối.

**Ghi nhớ:** `jpackage --type app-image` giúp tạo ứng dụng với **runtime Java đi kèm**, có thể chạy khi máy người dùng chưa cài JDK/JRE riêng. Để chứng minh điều đó, hãy kiểm thử native launcher trong môi trường **không có Java trên PATH**, rồi lặp lại trên **máy sạch thực sự**, cùng OS/kiến trúc mục tiêu. Kiểm tra cả thư viện native, resource, module và chức năng nghiệp vụ; không chỉ kiểm tra có launcher.

### Tham khảo chính thức còn áp dụng

- [JEP 392 — Packaging Tool, chuẩn từ JDK 16](https://openjdk.org/jeps/392)
- [Oracle JDK 25 — Packaging Overview và Java Runtime Requirements](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html)
- [Oracle JDK 25 — jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html)
- [Oracle JDK 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html)
- [Oracle JDK 21 — jpackage Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
