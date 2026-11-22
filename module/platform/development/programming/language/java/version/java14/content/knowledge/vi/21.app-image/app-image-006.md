# Bổ sung launcher cho các điểm vào khác nhau trong app image với `jpackage --add-launcher`

## 1. Bài học này giải quyết vấn đề gì?

Một ứng dụng Java có thể có **nhiều điểm vào (*entry points*)**: mở giao diện chính, chạy báo cáo, thực hiện thao tác quản trị, kiểm tra dữ liệu, hoặc khởi động cùng một chương trình với **tham số mặc định khác nhau**. Thay vì phát hành nhiều runtime Java độc lập, công cụ **`jpackage`** có thể tạo một **application image (`app-image`)** chứa:

- **Launcher chính**: được định nghĩa bởi các tùy chọn `--name`, `--main-jar`/`--module`, `--main-class`, `--arguments`, `--java-options`.
- **Một hoặc nhiều launcher bổ sung**: khai báo bằng **`--add-launcher launcherName=propertiesFile`**.
- **Payload ứng dụng** và một **runtime image** đóng gói chung (tạo qua `jlink` hoặc cung cấp bằng `--runtime-image`).
- Các executable/điểm khởi động theo **hệ điều hành đích**, mỗi launcher có cấu hình điểm vào riêng.

Ví dụ minh họa trên Windows sau khi đóng gói:

```text
out/
└── LearningTools/
    ├── LearningTools.exe    ← demo.AppMain
    ├── ReportTool.exe       ← demo.ReportMain
    ├── AdminTool.exe        ← demo.AdminMain
    ├── app/                  ← dữ liệu ứng dụng đóng gói
    └── runtime/              ← Java runtime dùng chung
```

Đây là sơ đồ khái niệm của **app-image Windows**; các file cấu hình, thư mục phụ có thể khác theo phiên bản JDK. Tên và vị trí launcher trên Linux/macOS cũng khác, nên không copy đường dẫn `.exe` sang hai hệ điều hành đó.

**Tính hiện hành:** `jpackage` lần đầu xuất hiện ở **JDK 14** với trạng thái *incubating* (JEP 343), tiếp tục incubating ở JDK 15 và trở thành công cụ **production-ready từ JDK 16** (JEP 392). Trong JDK hiện đại, module là `jdk.jpackage`, **không** dùng tên module incubator `jdk.incubator.jpackage` hoặc các lệnh dành riêng cho giai đoạn thử nghiệm. Bài sử dụng công cụ và cú pháp được duy trì trong Java 17+, Java 21+, Java 25/26.

## 2. Phân biệt launcher, entry point, app image và installer

| Khái niệm | Vai trò | Điều không nên nhầm |
| --- | --- | --- |
| **Entry point** | Method `public static void main(String[] args)` của class, hoặc main class trong module | Đây là logic Java, **không** tự tạo file chạy native |
| **Launcher** | Chương trình khởi động native do `jpackage` tạo, biết gọi Java entry point và truyền args/JVM options | Không phải một Java runtime riêng cho từng launcher |
| **Launcher chính** | Được khai báo ngay trên command line `jpackage` | Không cần `--add-launcher` cho launcher chính |
| **Launcher bổ sung** | Được khai báo qua `--add-launcher name=propertiesFile` | Không nhất thiết là một ứng dụng độc lập khác; có thể chỉ là một chế độ chạy khác |
| **App image** | Thư mục ứng dụng với launcher, payload và runtime cần thiết | Không phải `.msi`/`.exe installer` chỉ vì trong thư mục có launcher executable |
| **Installer native** | Gói cài đặt hệ điều hành như MSI/EXE, PKG/DMG, DEB/RPM | Được tạo bằng `jpackage` với loại package phù hợp, cần công cụ/điều kiện của host |

`jpackage --type app-image` tạo **thư mục ứng dụng có thể chạy**. Nếu muốn tạo bộ cài, có thể tạo một package native riêng từ cấu hình hoặc từ app image đã tạo theo khả năng của phiên bản JDK. **Không cần bộ cài** để thử ba launcher trong ví dụ.

Điều cần nhớ: một `app-image` có thể có **nhiều launcher**, mỗi launcher chuyển tới một `main` khác nhau hoặc có arguments/JVM options riêng, nhưng thường **dùng chung payload và runtime**.

## 3. Cú pháp `--add-launcher` và cách hoạt động

Cú pháp tổng quát:

```text
jpackage ... --add-launcher launcher-name=path/to/launcher.properties
```

- `launcher-name`: tên của launcher bổ sung; trong ví dụ Windows có tên `ReportTool`, kết quả là executable `ReportTool.exe`.
- `path/to/launcher.properties`: **đường dẫn tới tệp Java properties** (có thể là tương đối hoặc tuyệt đối). File này cần **tồn tại lúc build**.
- **Mỗi launcher bổ sung có một file properties** và một lần dùng `--add-launcher`.
- Có thể **lặp `--add-launcher` nhiều lần** để thêm nhiều điểm vào.
- `jpackage` tạo launcher chính từ **tùy chọn command line**, rồi dùng từng file properties để **kế thừa những tùy chọn chung, ghi đè các giá trị mà launcher phụ khai báo**.

Ví dụ:

```text
--name LearningTools
--main-jar app.jar
--main-class demo.AppMain
--arguments home
--java-options -Ddemo.mode=primary

--add-launcher ReportTool=report.properties
--add-launcher AdminTool=admin.properties
```

Launcher chính gọi `demo.AppMain`. Nếu `report.properties` có `main-class=demo.ReportMain`, `arguments=summary "North Region"` và `java-options=-Ddemo.mode=report`, launcher `ReportTool` chạy **`demo.ReportMain`**, không chạy `demo.AppMain`. Nếu launcher phụ **không chỉ định `main-jar`**, nó tiếp tục dùng JAR chính được khai báo từ command line.

### 3.1. Những khóa thường dùng trong properties file

| Khóa | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `main-class` | Java class có điểm vào cần chạy | `main-class=demo.ReportMain` |
| `main-jar` | JAR chính cho launcher classpath, relative với `--input` | `main-jar=reports.jar` |
| `module` | Module/name của class chính cho ứng dụng modular | `module=com.example.reports/com.example.reports.Main` |
| `arguments` | Tham số ứng dụng **mặc định**, dùng khi người dùng không đưa arguments lúc gọi launcher | `arguments=summary "North Region"` |
| `java-options` | Tùy chọn JVM của launcher đó | `java-options=-Ddemo.mode=report` |
| `icon` | Icon riêng của launcher nếu muốn và platform hỗ trợ | `icon=icons/report.ico` trên Windows |
| `win-console` | Chọn launcher Windows dạng console | `win-console=true` |

Theo tài liệu `jpackage` hiện hành, file properties còn có một số khóa như `description`, `launcher-as-service` và tùy chọn tạo menu/shortcut theo platform. **Không phải khóa nào cũng có mặt trên mọi JDK/platform**: xem tài liệu **của chính JDK dùng để đóng gói** và chọn các khóa thực sự cần thiết.

Chú ý:
- `main-class` dùng với cách đóng gói **`--main-jar`**, không dùng `--module` và `--main-jar` đồng thời.
- `module` dành cho trường hợp đóng gói ứng dụng modular.
- `arguments` không tương đương `java-options`: cái đầu truyền vào `main(String[] args)`, cái sau truyền cho JVM (ví dụ `-D` hoặc cấu hình heap).
- `win-console` là cấu hình **chỉ áp dụng Windows**. Trên Linux/macOS, bỏ tùy chọn này và chọn launchers/GUI integration phù hợp.
- File properties **không phải** nơi an toàn để lưu mật khẩu, token hoặc bí mật, vì cấu hình có thể hiện diện trong output/bundle và bị kiểm tra.

## 4. Hai kiểu launcher bổ sung thường gặp

### 4.1. Điểm vào khác class `main`

Giả sử ứng dụng có:

```text
demo.AppMain        → mở hoặc chạy chức năng chính
demo.ReportMain     → tạo báo cáo
demo.AdminMain      → công cụ quản trị/kiểm tra
```

Cả ba class có thể nằm trong cùng `app.jar`. Launcher bổ sung chỉ cần khai báo **`main-class`** và những tùy chọn khác biệt; không bắt buộc phải tạo ba JAR riêng.

Ví dụ `report.properties`:

```properties
main-class=demo.ReportMain
arguments=summary "North Region"
java-options=-Ddemo.mode=report
win-console=true
```

Ví dụ `admin.properties`:

```properties
main-class=demo.AdminMain
arguments=check
java-options=-Ddemo.mode=admin
win-console=true
```

Trong cả hai file, **không** có `main-jar`, vì chúng kế thừa `app.jar` từ launcher chính. Điều kiện cần là các class `demo.ReportMain` và `demo.AdminMain` **thực sự nằm trong JAR đóng gói** và có method `main` hợp lệ.

### 4.2. Cùng class `main` nhưng chế độ chạy khác

Đôi khi điểm vào **giữ nguyên một class** nhưng launcher có arguments khác nhau. Ví dụ class `demo.AppMain` phân tích `args[0]`:

```properties
arguments=diagnose
java-options=-Ddemo.mode=diagnostic
```

Nếu không có `main-class` thì launcher phụ **kế thừa main class chính**; khi chạy launcher phụ không truyền args, Java main nhận `"diagnose"` thay vì `"home"`. Điều này phù hợp với các lối tắt “mở app thông thường”, “chạy công cụ chẩn đoán”, “chạy job định kỳ” có cùng codebase.

Tuy nhiên, không nên lạm dụng việc dùng arguments để phân chia các quyền nghiệp vụ. **Tên launcher `AdminTool` không làm người dùng có đặc quyền quản trị**. Kiểm tra xác thực, ủy quyền và quy định bảo mật vẫn phải được thực thi trong logic Java và phía hệ thống.

## 5. Chuẩn bị dự án ví dụ hoàn chỉnh (Java 17+)

Ví dụ này dùng **bốn file Java** trong package `demo`. Cả ba launcher sẽ:

1. Ghi tên entry class đang chạy.
2. Ghi arguments đã được launcher truyền vào.
3. Ghi Java system property `demo.mode` để chứng minh `java-options` được áp dụng riêng.
4. Ghi kết quả vào file nhỏ trong một **thư mục test độc lập** đã chỉ định qua environment variable `JPACKAGE_DEMO_OUTPUT`, đồng thời in stdout.

Cách ghi ra thư mục test độc lập tránh yêu cầu app image phải có quyền ghi vào chính thư mục đã đóng gói.

Cấu trúc đầu vào:

```text
project/
├── src/
│   └── demo/
│       ├── DemoOutput.java
│       ├── AppMain.java
│       ├── ReportMain.java
│       └── AdminMain.java
├── report.properties
├── admin.properties
├── classes/                ← được javac tạo
├── input/
│   └── app.jar             ← được jar tạo
├── out/                   ← được jpackage tạo
└── logs/                  ← output chạy thử
```

### 5.1. File `src/demo/DemoOutput.java`

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;

public final class DemoOutput {
    private DemoOutput() {}

    public static void record(String name, String[] args) throws Exception {
        String text = "entry=" + name + "\nargs=" + String.join("|", args)
                + "\nmode=" + System.getProperty("demo.mode", "unset") + "\n";

        Path dir = Path.of(System.getenv("JPACKAGE_DEMO_OUTPUT"));
        Files.writeString(dir.resolve(name + ".txt"), text);
        System.out.print(text);
    }
}
```

Method `record` nhận tên entry point, nối arguments bằng dấu `|` và đọc `-Ddemo.mode` từ JVM. `System.getenv("JPACKAGE_DEMO_OUTPUT")` **phải được đặt** trước khi chạy demo; nếu biến môi trường thiếu, đoạn minh họa có thể thất bại vì path không có giá trị. Phần hướng dẫn chạy ở mục 7 sẽ đặt biến này.

Trong ứng dụng thật, không cần ép mọi launcher ghi log vào file như vậy; đây chỉ là cơ chế kiểm thử đầu ra **độc lập và dễ đối chiếu**.

### 5.2. File `src/demo/AppMain.java`

```java
package demo;

public class AppMain {
    public static void main(String[] args) throws Exception {
        DemoOutput.record("AppMain", args);
    }
}
```

Đây là **entry point chính**. Khi chạy với launcher `LearningTools`, dự kiến nhận argument `home` và system property `demo.mode=primary`.

### 5.3. File `src/demo/ReportMain.java`

```java
package demo;

public class ReportMain {
    public static void main(String[] args) throws Exception {
        DemoOutput.record("ReportMain", args);
    }
}
```

Đây là **entry point báo cáo**. `report.properties` chỉ định `main-class=demo.ReportMain`, arguments mặc định gồm **hai phần tử** `summary` và `North Region`; dấu nháy kép trong properties bảo đảm nhóm thứ hai là **một argument có khoảng trắng**.

### 5.4. File `src/demo/AdminMain.java`

```java
package demo;

public class AdminMain {
    public static void main(String[] args) throws Exception {
        DemoOutput.record("AdminMain", args);
    }
}
```

Đây là entry point quản trị **chỉ về tên gọi và chức năng Java của ví dụ**; nó không tự yêu cầu hay tự cấp quyền nâng cao trên Windows.

## 6. File properties cho launcher báo cáo và launcher quản trị

Tạo hai file cùng cấp với thư mục `src`.

**`report.properties`**:

```properties
main-class=demo.ReportMain
arguments=summary "North Region"
java-options=-Ddemo.mode=report
win-console=true
```

**`admin.properties`**:

```properties
main-class=demo.AdminMain
arguments=check
java-options=-Ddemo.mode=admin
win-console=true
```

Các dòng `win-console=true` có ích cho **demo trên Windows**, vì các entry points in stdout. Với app GUI, có thể không muốn launcher console mở cửa sổ; với Linux/macOS hãy bỏ dòng `win-console`.

**Vì sao không cần `main-jar=app.jar` trong cả hai file?** `--add-launcher` tạo launcher thay thế dựa trên các tùy chọn của launcher chính. Chỉ `main-class`, `arguments` và `java-options` được ghi đè; `main-jar` được kế thừa nếu không chỉ định lại.

Các properties là dữ liệu **cấu hình build**. Không chép nguyên thông tin bí mật, mật khẩu cơ sở dữ liệu, token API vào `java-options=-Dsecret=...` vì người dùng có quyền đọc image có thể thấy các cài đặt đó.

## 7. Biên dịch, tạo JAR và chạy `jpackage` (Windows PowerShell)

Ví dụ dùng **PowerShell** trên Windows, trong thư mục `project` nói ở mục 5. Trên Linux/macOS, cú pháp shell và đường dẫn executable khác, nhưng tư tưởng `--add-launcher` giống nhau.

### 7.1. Kiểm tra công cụ

```powershell
java -version
javac -version
jar --version
jpackage --version
```

`jpackage` là **công cụ của JDK**, không phải một thư viện Maven dependency cần thêm vào Java source. Nên sử dụng JDK có `jpackage` hiện hành, tối thiểu từ Java 16 cho trạng thái production-ready, và đóng gói trên **chính loại hệ điều hành đích**. Ví dụ đã được kiểm chứng với JDK 24.0.2 trên Windows, trong khi mã Java được biên dịch với `--release 17` để tương thích API Java 17.

### 7.2. Tạo thư mục và biên dịch tất cả entry points

```powershell
$dirs = @(".\src\demo", ".\classes", ".\input", ".\out", ".\logs")
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

$srcFiles = Get-ChildItem ".\src\demo\*.java" |
        ForEach-Object { $_.FullName }

javac --release 17 -d .\classes $srcFiles
jar --create --file .\input\app.jar -C .\classes .
jar --list --file .\input\app.jar
```

Kết quả `jar --list` có thể chứa metadata và những entry tương tự:

```text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/AdminMain.class
demo/AppMain.class
demo/DemoOutput.class
demo/ReportMain.class
```

**Điều kiện quan trọng:** trong `app.jar` phải có **tất cả** main classes mà các launcher phụ tham chiếu. Trong lệnh build phía dưới, `--main-jar app.jar` được hiểu là file `app.jar` **tương đối với `--input input`**, không phải một file cần được tìm trong thư mục `src`.

JAR này được tạo không cần `Main-Class` trong manifest, vì `jpackage` sẽ được chỉ rõ `--main-class demo.AppMain` và từng launcher phụ có `main-class` riêng. Nếu một JAR có manifest khác, vẫn nên truyền cấu hình tường minh để tránh entry point bị xác định sai.

### 7.3. Tạo một app image với ba launchers

```powershell
$jpackageArgs = @(
    "--type", "app-image",
    "--dest", "out",
    "--name", "LearningTools",
    "--input", "input",
    "--main-jar", "app.jar",
    "--main-class", "demo.AppMain",
    "--arguments", "home",
    "--java-options", "-Ddemo.mode=primary",
    "--win-console",
    "--add-launcher", "ReportTool=report.properties",
    "--add-launcher", "AdminTool=admin.properties"
)

jpackage @jpackageArgs
```

Phần `@jpackageArgs` là **PowerShell argument splatting**, chỉ dùng để gửi các phần tử argument cho lệnh `jpackage`; không phải Java annotation hay một tùy chọn đặc biệt của `jpackage`. Có thể viết tất cả thành một dòng CLI tương đương nếu muốn.

Kết quả trên Windows là thư mục `out\LearningTools` gồm các executables:

```text
LearningTools.exe
ReportTool.exe
AdminTool.exe
```

Các file `.exe` trên cùng dùng **runtime và payload được đóng gói trong app image**. Lệnh tạo image đã được chạy thành công trong môi trường test Windows/JDK 24.0.2; không cần cài đặt MSI hoặc WiX chỉ để tạo `--type app-image`.

### 7.4. Chạy từng launcher và đối chiếu kết quả

Trước khi chạy, đặt biến môi trường mà `DemoOutput` dùng để ghi file kiểm thử:

```powershell
$env:JPACKAGE_DEMO_OUTPUT = (Resolve-Path .\logs).Path

.\out\LearningTools\LearningTools.exe
.\out\LearningTools\ReportTool.exe
.\out\LearningTools\AdminTool.exe
```

**Stdout đã kiểm chứng** khi chạy lần lượt:

```text
entry=AppMain
args=home
mode=primary
entry=ReportMain
args=summary|North Region
mode=report
entry=AdminMain
args=check
mode=admin
```

Đây là **ba khối output**, mỗi launcher có ba dòng. Đồng thời có các tệp `logs\AppMain.txt`, `logs\ReportMain.txt` và `logs\AdminMain.txt` chứa đúng các dòng tương ứng.

Kết luận từ output:

1. **`LearningTools.exe` gọi `demo.AppMain`** với default argument `home`, JVM property `demo.mode=primary`.
2. **`ReportTool.exe` gọi `demo.ReportMain`** với hai default arguments `summary` và `North Region`, property `demo.mode=report`.
3. **`AdminTool.exe` gọi `demo.AdminMain`** với default argument `check`, property `demo.mode=admin`.
4. Cả ba launcher nằm trong **cùng một app-image**. Chỉ đổi file launcher được chạy đã chọn một Java main class khác, không cần chuyển classpath thủ công tại runtime.

### 7.5. Tham số người dùng truyền trực tiếp có thể thay thế `arguments` mặc định

Theo tài liệu `jpackage`, default `--arguments` hoặc `arguments` trong properties chỉ được dùng **khi người dùng không truyền arguments vào launcher**. Ví dụ:

```powershell
.\out\LearningTools\ReportTool.exe custom
```

**Kết quả đã kiểm chứng:**

```text
entry=ReportMain
args=custom
mode=report
```

Lần này `ReportMain` nhận **`custom`**, không phải `summary|North Region`. Điều đó không làm đổi main class hoặc JVM property: chỉ các arguments mặc định của ứng dụng bị thay bằng arguments được cung cấp ở lúc chạy.

**Đừng nhầm:** arguments đi **sau** tên launcher là các **tham số ứng dụng**; `--java-options` là tùy chọn JVM đã cố định vào launcher khi build, không phải các flags có thể tùy ý thêm từ CLI của launcher đã đóng gói.

## 8. Kế thừa và ghi đè cấu hình launcher

`--add-launcher` tạo **alternative launchers** từ cấu hình chung của launcher chính, sau đó áp dụng các khóa riêng của file properties.

| Thuộc tính | Launcher chính `LearningTools` | `ReportTool` | `AdminTool` |
| --- | --- | --- | --- |
| `main-jar` | `app.jar` | Kế thừa `app.jar` | Kế thừa `app.jar` |
| `main-class` | `demo.AppMain` | `demo.ReportMain` | `demo.AdminMain` |
| Default `arguments` | `home` | `summary "North Region"` | `check` |
| `java-options` | `-Ddemo.mode=primary` | `-Ddemo.mode=report` | `-Ddemo.mode=admin` |
| Windows console | `--win-console` | `win-console=true` | `win-console=true` |
| Runtime | Image của `LearningTools` | Chia sẻ | Chia sẻ |

Trong JDK đã thử, thiết lập `java-options=-Ddemo.mode=report` của `ReportTool` ghi đè tùy chọn JVM ở launcher chính đúng như hợp đồng. Nếu muốn **giữ các tùy chọn JVM chung và bổ sung tùy chọn riêng**, hãy thiết kế list `java-options` tương ứng một cách tường minh và kiểm tra thứ tự/độ ưu tiên, tránh mặc định rằng mọi giá trị được cộng dồn như bạn kỳ vọng.

### 8.1. Launcher khác cùng JAR so với launcher khác JAR

**Trường hợp cùng JAR (demo):** tất cả main classes nằm trong `app.jar`; thêm properties chứa `main-class` là đủ.

**Trường hợp nhiều JAR:** có thể đóng gói các JAR cần thiết vào `--input`, rồi đặt `main-jar=reports.jar` và `main-class=...` trong properties tương ứng nếu muốn launcher phụ có JAR chính khác. **Đừng** chỉ tham chiếu một `reports.jar` không có trong payload; launcher có thể được tạo nhưng sẽ không khởi động đúng nếu thiếu class/dependency. Phải xác minh classpath, các dependencies và chạy thử mọi launcher trên image thực.

Không coi `--add-launcher` là cơ chế tự động tải dependency từ Maven Central. `jpackage` đóng gói **các tài nguyên/dependencies do build cung cấp**, không chạy Maven/Gradle để tự giải quyết phần thiếu.

## 9. Trường hợp ứng dụng modular (`--module`)

Khi code là ứng dụng Java **module** có `module-info.java` và các module được build trước, điểm vào chính có thể được xác định bằng:

```text
--module com.example.app/com.example.app.Main
```

Một launcher phụ có thể dùng file properties:

```properties
module=com.example.tools/com.example.tools.ReportMain
arguments=summary
```

Đây là **mẫu cấu hình minh họa**, không phải bản build runnable của chương trình 4 file ở mục 5 (mục 5 dùng non-modular JAR). Với modular app:

- Dùng `--module-path`/`-p` chứa các module cần thiết.
- **Không trộn `--module` và `--main-jar`** cho cùng cấu hình launcher.
- Đảm bảo runtime image tạo bởi `jlink` có **cả module** chứa entry point phụ và dependencies của module đó. Khi cần, bổ sung modules qua `--add-modules` hoặc tạo runtime image thích hợp rồi dùng `--runtime-image`.
- Kiểm tra các module path, tên main class có thể truy cập, và chạy thử launcher phụ trên đúng platform.

Điểm quan trọng: thêm `module=...` trong file launcher **không thể khôi phục** một module bị loại khỏi runtime image khi build. Nếu launcher phụ chạy vào module khác, phải bảo đảm runtime chứa các module tương ứng.

## 10. App image trên Windows, Linux và macOS

`jpackage` hỗ trợ tạo output theo host, nhưng **không hỗ trợ cross-platform packaging trực tiếp**. Một build chạy trên Windows tạo image/bundle kiểu Windows; để tạo image cho Linux hoặc macOS, chạy `jpackage` trên hệ điều hành tương ứng.

| Nền tảng | Launcher có hình thức phổ biến | Lưu ý |
| --- | --- | --- |
| Windows | File `.exe` trong application image | `--win-console`/`win-console=true` có ích cho CLI; icon thường là `.ico` |
| Linux | File executable dưới cấu trúc image của Linux | Quyền thực thi, library system, shortcut và package DEB/RPM phụ thuộc môi trường |
| macOS | Launcher nằm trong bundle `.app` theo cấu trúc của macOS | Code signing/notarization và bundle metadata có thể quan trọng khi phân phối |

**`--type app-image` khác `--type exe/msi/deb/rpm/pkg/dmg`.** App image cho phép kiểm thử **cả ba launcher ngay từ output folder** trước khi tạo installer. Cách này đặc biệt hữu ích để tránh phát hiện lỗi `main-class` hoặc `arguments` sau khi đã đưa package cho người dùng.

### 10.1. Windows console và GUI launcher

Ứng dụng dòng lệnh cần xem stdout/stderr thường dùng:

```text
--win-console
```

với launcher chính và:

```properties
win-console=true
```

trong properties của launcher phụ. Với GUI JavaFX/Swing, có thể muốn launcher dạng GUI để không xuất hiện cửa sổ console. **Không sao chép `win-console` sang Linux/macOS.**

### 10.2. App image có thể được phân phối theo thư mục

Một app image thường được dùng để thử nội bộ, đóng gói lại hoặc tạo installer sau đó. Khi chuyển image sang máy khác, **giữ nguyên cấu trúc thư mục** và mọi file runtime/payload đi kèm; không copy riêng `ReportTool.exe` hoặc `AdminTool.exe` rồi kỳ vọng chúng hoạt động như standalone executable hoàn toàn độc lập.

App-image không phải lời bảo đảm chạy được trên mọi phiên bản hệ điều hành/CPU: khả năng tương thích phụ thuộc **OS, kiến trúc, native libraries**, việc ký ứng dụng và chính môi trường đích. Test trên OS/architecture mục tiêu.

## 11. Các bước kiểm thử multi-launcher trước khi phát hành

Một bảng kiểm thử tối thiểu cho ví dụ:

| Kiểm thử | Hành động | Kỳ vọng |
| --- | --- | --- |
| **L1 — main launcher** | Chạy `LearningTools.exe` không args | `entry=AppMain`, `args=home`, `mode=primary` |
| **L2 — report launcher** | Chạy `ReportTool.exe` không args | `entry=ReportMain`, `args=summary|North Region`, `mode=report` |
| **L3 — admin launcher** | Chạy `AdminTool.exe` không args | `entry=AdminMain`, `args=check`, `mode=admin` |
| **L4 — override mặc định** | Chạy `ReportTool.exe custom` | `entry=ReportMain`, `args=custom`, `mode=report` |
| **L5 — đủ classes** | Kiểm tra `jar --list --file input\app.jar` | Có `demo/AppMain.class`, `demo/ReportMain.class`, `demo/AdminMain.class` |
| **L6 — đủ native launchers** | Liệt kê file `.exe` trong app image | Có `LearningTools.exe`, `ReportTool.exe`, `AdminTool.exe` |
| **L7 — không phụ thuộc JDK ngoài** | Chạy trên máy test tương thích chỉ có app image | Launcher dùng runtime đóng gói, không bắt người dùng tự cài JDK đầy đủ |
| **L8 — lỗi thiếu file/dependency** | Thử bỏ một JAR cần thiết trong build thử nghiệm | Phát hiện sớm qua build/smoke test thay vì để lỗi tới production |

**Quan sát đã kiểm chứng:** trên Windows/JDK 24.0.2, `javac --release 17` biên dịch 4 class, `jar` tạo `app.jar`, `jpackage --type app-image` tạo **3 file .exe**, các launcher chạy với exit code 0, và cả bốn case L1–L4 cho đúng class/args/JVM property.

### 11.1. Test exit code và kết quả ngoài stdout

Với CLI, nên kiểm tra `$LASTEXITCODE` sau khi chạy từng executable trong PowerShell. Trong demo, 3 launchers và lần chạy override đều trả **0**. Đối với GUI app, stdout/exit code chưa chắc là dấu hiệu đủ: cần smoke test giao diện, kiểm tra log ứng dụng và các thư viện native/runtime tương ứng.

### 11.2. Test quyền truy cập và tài nguyên ghi

App image/installer có thể được đặt ở thư mục **không có quyền ghi cho user thường**. Trong demo, các log được ghi theo đường dẫn `JPACKAGE_DEMO_OUTPUT` trỏ vào `logs` của thư mục test do user sở hữu; không ghi mặc định vào cạnh launcher. Trong production, hãy chọn user-data directory phù hợp với hệ điều hành, không giả định application directory có thể sửa được.

## 12. Lỗi thường gặp khi thêm launcher

### Lỗi A — Chỉ tạo properties nhưng không dùng `--add-launcher`

`report.properties` nằm trên disk không có nghĩa `jpackage` tự quét và tạo `ReportTool.exe`. Phải truyền `--add-launcher ReportTool=report.properties` lúc build.

### Lỗi B — Dùng một file properties cho hai entry points khác nhau

Mỗi alternative launcher có cấu hình của riêng nó. Nếu muốn một launcher chạy `demo.ReportMain` và launcher khác chạy `demo.AdminMain`, hãy tạo **hai file** và truyền **hai lần `--add-launcher`**.

### Lỗi C — Gõ sai tên `main-class`

`main-class=ReportMain` không tương đương `main-class=demo.ReportMain` nếu class thực thuộc package `demo`. Java runtime có thể báo không tìm thấy main class hoặc lỗi khởi động. Xác nhận bằng `jar --list` và thử `java -cp input\app.jar demo.ReportMain` (với environment cho demo) trước khi gọi `jpackage`.

### Lỗi D — Không đưa JAR/dependencies vào `--input`

`--main-jar app.jar` tìm trong input directory. Nếu class phụ nằm trong JAR khác, phải đưa JAR/dependencies đó vào payload và chỉ định cách chạy tương ứng. `jpackage` không tự giải quyết dependency qua Maven/Gradle.

### Lỗi E — Nhầm `--arguments` với `--java-options`

`arguments=summary` trở thành một phần của `String[] args` trong Java main. `java-options=-Ddemo.mode=report` thiết lập Java system property. Đưa `-D...` vào `arguments` chỉ làm Java main nhìn thấy một chuỗi, không tự định nghĩa system property.

### Lỗi F — Tưởng arguments mặc định luôn được nối thêm

Nếu người dùng chạy `ReportTool.exe custom`, arguments mặc định của launcher có thể bị **thay thế** bằng `custom`, như kiểm thử L4. Không dựa vào `arguments=...` như cơ chế bắt buộc để ép user đi qua một nhánh nghiệp vụ nhạy cảm.

### Lỗi G — Dùng cấu hình `win-console` trên nền tảng không phải Windows

`win-console=true` là tùy chọn Windows. Giữ properties theo OS hoặc bỏ hẳn dòng này trên platform khác. Kiểm tra cả launcher chính và phụ nếu muốn xem stdout của ứng dụng CLI.

### Lỗi H — Ghi đè launcher config nhưng quên những settings chung

Một launcher có `java-options` khác có thể ghi đè tùy chọn ở launcher chính. Nếu cả hai cần `-Dfile.encoding` hoặc thiết lập JVM khác, kiểm tra cấu hình cuối cùng của từng launcher; không mặc định mọi option được kế thừa cộng dồn.

### Lỗi I — Tạo launcher phụ chạy module bị loại khỏi runtime

Với modular app, runtime do `jlink` tạo có thể không bao gồm module chỉ được dùng bởi launcher phụ. Bổ sung module khi build hoặc cung cấp runtime image phù hợp, rồi chạy smoke test để phát hiện `Module ... not found`.

### Lỗi J — Chỉ chuyển một file .exe ra ngoài image

Native launcher của `jpackage` thường phụ thuộc runtime, JAR payload và các file cấu hình cùng image. Copy riêng executable sang thư mục khác dễ gây lỗi. Phân phối **toàn bộ app image** hoặc installer được tạo từ nó.

### Lỗi K — Dùng đường dẫn chứa dấu cách mà không quote

Với file properties nằm ở `C:\Work Files\report.properties`, hãy truyền cả argument `name=path` thành **một đối số duy nhất**, ví dụ trong PowerShell `"ReportTool=C:\Work Files\report.properties"`. File properties cũng cần quote các default arguments có khoảng trắng theo cú pháp jpackage, ví dụ `arguments=summary "North Region"`.

### Lỗi L — Nhầm native launcher với security boundary

`AdminTool.exe` chỉ mở một điểm vào do bạn đặt tên. Nó **không tự xác thực tài khoản**, **không cấp quyền administrator** và **không tách sandbox**. Vẫn phải kiểm soát các operations nhạy cảm trong code Java và dịch vụ backend.

### Lỗi M — Dùng hướng dẫn `jdk.incubator.jpackage` cũ

Module `jdk.incubator.jpackage` thuộc giai đoạn incubator của Java 14–15. Java 16+ đã chuyển sang công cụ chuẩn `jdk.jpackage`; trong dự án hiện đại dùng `jpackage` có sẵn trong JDK, không chép lại các flags cũ từ hướng dẫn incubator mà chưa kiểm tra.

### Lỗi N — Tưởng `--add-launcher` chạy được từ `java`

`--add-launcher` là tùy chọn của **công cụ `jpackage` khi tạo package/image**, không phải của `java` và không phải argument cho executable sau khi đóng gói. Muốn thay launcher properties, **rebuild image/package** theo quy trình build, thay vì kỳ vọng file `report.properties` bên ngoài sẽ được launcher xử lý lại tùy ý sau phát hành.

## 13. Bài tập tự đánh giá

**Câu 1.** Muốn một app image có 1 launcher chính và 2 launchers phụ, phải có bao nhiêu lần `--add-launcher`?

**Đáp án:** **Hai lần**. Launcher chính được xác định từ command line; mỗi launcher phụ cần một file properties và một lần `--add-launcher`.

**Câu 2.** `report.properties` chỉ có `main-class=demo.ReportMain`, trong khi command line dùng `--main-jar app.jar --main-class demo.AppMain`. Launcher phụ sẽ dùng JAR nào?

**Đáp án:** Dùng **`app.jar`** được kế thừa; điểm vào được ghi đè thành `demo.ReportMain`, với điều kiện class này nằm trong JAR.

**Câu 3.** Muốn truyền `-Ddemo.mode=report` vào JVM, nên đặt trong `arguments` hay `java-options`?

**Đáp án:** `java-options`. `arguments` được truyền cho `main(String[] args)`, còn `-Ddemo.mode=report` là system property của JVM.

**Câu 4.** Vì sao `arguments=summary "North Region"` có dấu nháy kép?

**Đáp án:** Để giá trị `North Region` có khoảng trắng được truyền như **một** argument. Trong demo, `args` có hai phần tử: `summary` và `North Region`.

**Câu 5.** Nếu chạy `ReportTool.exe custom`, Java main nhận những default arguments nào?

**Đáp án:** Nhận **`custom`** thay cho các default arguments vì người dùng đã truyền arguments ở thời điểm chạy launcher. Demo xác nhận `args=custom`.

**Câu 6.** `--type app-image` và `--type msi` có giống nhau không?

**Đáp án:** Không. `app-image` là thư mục ứng dụng có thể chạy; MSI là **native installer** Windows, có thêm yêu cầu và workflow đóng gói riêng.

**Câu 7.** Có thể dùng `jpackage` trên Windows để trực tiếp tạo file `.app` macOS không?

**Đáp án:** Không. Công cụ đóng gói theo nền tảng host, không hỗ trợ build package trực tiếp xuyên platform; cần chạy trên macOS để tạo bundle/app image cho macOS.

**Câu 8.** Nếu thêm launcher phụ gọi main class ở một module khác, điều gì cần kiểm tra?

**Đáp án:** Module đó và dependencies phải có trong module path/runtime image, đồng thời main class phải chạy được; `module=...` trong properties không tự làm xuất hiện module bị bỏ khỏi runtime.

**Câu 9.** `AdminTool.exe` có tự nâng quyền quản trị hệ điều hành khi chạy không?

**Đáp án:** Không. Tên launcher không cấp quyền. Phải dùng cơ chế xác thực, ủy quyền và kiểm soát quyền chính thức của ứng dụng/hệ điều hành.

**Câu 10.** Vì sao nên chạy smoke test từng launcher ngay khi tạo `app-image`?

**Đáp án:** Vì mỗi launcher có thể chứa lỗi main class, argument quoting, JVM options, missing dependency hoặc module riêng. Kiểm thử tại giai đoạn app-image phát hiện lỗi **trước khi tạo installer và phân phối**.

## 14. Checklist khi triển khai multi-launcher trong dự án

- [ ] Dùng JDK có `jpackage` chuẩn (**Java 16+**), ưu tiên JDK phù hợp pipeline phát hành; không dựa vào module incubator cũ.
- [ ] Xác định rõ entry point chính và các entry points bổ sung; mọi class cần có `public static void main(String[] args)` hoặc module main hợp lệ.
- [ ] Chọn đúng kiểu đóng gói: non-modular `--main-jar` hoặc modular `--module`, không trộn vô lý.
- [ ] Gom đủ JAR, classes, resources và dependencies vào `--input`/module path.
- [ ] Tạo **một properties file cho mỗi launcher phụ** và truyền **một `--add-launcher` tương ứng**.
- [ ] Dùng `main-class` hoặc `module` để chỉ định điểm vào; dùng `arguments` để đặt default args, `java-options` để cấu hình JVM.
- [ ] Kiểm tra tên launcher không trùng và có ý nghĩa; tránh phụ thuộc đường dẫn không được quote khi có khoảng trắng.
- [ ] Đối với console app Windows, kiểm tra `--win-console` và `win-console=true`; không áp dụng khóa Windows trên hệ khác.
- [ ] Nếu launcher phụ thuộc module khác hoặc JAR khác, kiểm tra runtime image và dependencies thực.
- [ ] Tạo **`--type app-image`** trước để chạy mọi launcher; xác minh class/args/JVM options/exit code hoặc kết quả GUI.
- [ ] Kiểm tra behavior khi có arguments do user cung cấp, vì có thể thay thế default `arguments`.
- [ ] Không lưu bí mật trực tiếp trong launcher properties; không suy ra quyền bảo mật từ tên launcher.
- [ ] Phân phối **đầy đủ thư mục app image** hoặc tạo installer từ output; không copy riêng executable.
- [ ] Test trên từng OS/architecture mục tiêu; `jpackage` **không** build native package cross-platform.
- [ ] Khi thay entry point/properties, rebuild image theo CI/CD và kiểm chứng lại tất cả launcher.

## 15. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 26 — Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/26/jpackage/index.html): hướng dẫn đóng gói app images, ứng dụng có nhiều launcher, tùy chỉnh môi trường và platform.
2. [Oracle Java SE 25 — `jpackage` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): `--type app-image`, `--input`, `--main-jar`, `--main-class`, `--module`, `--add-launcher` và các khóa properties đang được hỗ trợ.
3. [Oracle Java SE 21 — Support Application Requirements / Add Launchers](https://docs.oracle.com/en/java/javase/21/jpackage/support-application-features.html): ví dụ định nghĩa thêm launcher bằng properties và arguments khác nhau.
4. [Oracle Java SE 27 — `jpackage` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html): đối chiếu cú pháp `--add-launcher` và danh sách option hiện hành.
5. [Oracle JDK 16 Release Notes — JEP 392](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): `jpackage` chuyển từ incubating (JDK 14–15) sang production-ready (JDK 16), module đổi thành `jdk.jpackage`.
6. [Oracle Java SE 17 — `jpackage` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): hướng dẫn tương thích khi dùng JDK 17.
