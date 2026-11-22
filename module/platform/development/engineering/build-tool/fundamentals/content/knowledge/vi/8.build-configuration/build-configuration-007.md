# Đường dẫn tương đối, đường dẫn tuyệt đối và khả năng di chuyển dự án

Build tool thường phải đọc mã nguồn, tài nguyên, tệp cấu hình, thư viện và ghi kết quả biên dịch hoặc báo cáo ra đĩa. Mỗi thao tác đều cần xác định vị trí tệp. Nếu đường dẫn được khai báo không đúng, build có thể chạy trên máy của người viết nhưng thất bại khi đồng đội checkout dự án ở thư mục khác hoặc khi CI chạy trên một hệ điều hành khác.

Hai loại đường dẫn cơ bản là:

- **Đường dẫn tuyệt đối (absolute path):** chỉ rõ vị trí từ gốc của hệ thống tệp, ví dụ `/opt/tools/checkstyle.xml` trên Linux hoặc `D:/tools/checkstyle.xml` trên Windows.
- **Đường dẫn tương đối (relative path):** mô tả vị trí so với một thư mục gốc đã biết, ví dụ `config/checkstyle.xml` hoặc `../shared/config.yml`.

Đường dẫn tương đối giúp cấu hình gắn với cấu trúc dự án thay vì vị trí checkout trên một máy cụ thể. Để dùng đúng, cần hiểu thư mục gốc mà build tool lấy làm mốc. Đường dẫn trong lệnh Terminal thường được tính từ thư mục làm việc hiện tại của Terminal; đường dẫn trong build script được giải quyết theo quy tắc của build tool và project tương ứng.

## 1. Đường dẫn tuyệt đối và đường dẫn tương đối

### Đường dẫn tuyệt đối

Đường dẫn tuyệt đối mô tả vị trí bắt đầu từ gốc của hệ thống tệp. Ví dụ:

```text
Linux:
/home/lan/work/java-app/config/app.yml

Windows:
C:/Users/Lan/work/java-app/config/app.yml
D:/tools/checkstyle/checkstyle.xml
```

Trên Windows, đường dẫn cũng có thể dùng dấu gạch chéo ngược:

```text
C:\Users\Lan\work\java-app\config\app.yml
```

Đường dẫn tuyệt đối hữu ích khi cần tham chiếu đến một vị trí đã được xác định bởi môi trường, chẳng hạn thư mục cài đặt một công cụ dùng chung hoặc một thư mục dữ liệu do hệ thống quản trị cấp phát. Tuy nhiên, đường dẫn tuyệt đối thường phụ thuộc vào:

- Tên người dùng trên máy.
- Ổ đĩa hoặc điểm mount.
- Cấu trúc thư mục đã cài đặt.
- Hệ điều hành và môi trường chạy.
- Vị trí checkout của repository.

Ví dụ, đường dẫn `C:/Users/Lan/work/java-app/config/app.yml` có thể tồn tại trên máy của Lan nhưng không tồn tại trên máy của Minh, dù hai người đang dùng cùng một commit. Đây là nguyên nhân phổ biến khiến build thiếu tính di động.

### Đường dẫn tương đối

Đường dẫn tương đối chỉ có ý nghĩa khi biết thư mục gốc dùng làm mốc. Ví dụ, với cấu trúc:

```text
java-app/
├── build.gradle
├── config/
│   └── app.yml
└── src/
    └── main/
        └── java/
            └── com/example/App.java
```

Đường dẫn `config/app.yml` trỏ đến tệp cấu hình nếu được giải quyết từ thư mục gốc `java-app`. Nếu thư mục dự án được chuyển từ `C:/work/java-app` sang `/workspace/java-app`, đường dẫn tương đối vẫn mô tả cùng vị trí bên trong dự án.

Một số ký hiệu thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `.` | Thư mục hiện tại hoặc thư mục gốc đang dùng làm mốc. |
| `..` | Thư mục cha của thư mục hiện tại. |
| `config/app.yml` | Đi vào thư mục `config`, sau đó tìm `app.yml`. |
| `../shared/common.yml` | Đi lên một cấp rồi vào `shared`. |
| `./gradlew` | Gọi wrapper trong thư mục hiện tại của shell. |

Không có một thư mục gốc chung cho mọi đường dẫn tương đối. Mốc phụ thuộc nơi đường dẫn được sử dụng. Cùng chuỗi `config/app.yml` có thể trỏ đến hai tệp khác nhau nếu được giải quyết từ hai thư mục khác nhau.

### Đường dẫn tương đối trong Terminal và trong build script

Đây là điểm cần phân biệt rõ:

- Khi bạn gõ `cat config/app.yml`, `Get-Content config/app.yml` hoặc `./gradlew`, shell giải quyết đường dẫn tương đối từ thư mục làm việc hiện tại của Terminal.
- Trong Gradle, `Project.file("config/app.yml")` giải quyết đường dẫn tương đối từ thư mục của project (`projectDir`) tương ứng.
- Trong Maven, nhiều đường dẫn cấu hình được giải quyết tương đối với thư mục dự án, được biểu diễn bởi `${project.basedir}`.

Ví dụ, bạn có thể đang đứng ở thư mục cha `workspace/` và gọi:

```shell
./java-app/gradlew -p java-app build
```

Đường dẫn `./java-app/gradlew` được shell giải quyết từ `workspace/`. Tham số `-p java-app` yêu cầu Gradle dùng `java-app` làm project directory cho build. Các đường dẫn được khai báo bằng API của `Project` sau đó tuân theo thư mục project của Gradle, không đơn giản lấy thư mục Terminal làm mốc cho mọi trường hợp.

Khi một tác vụ chạy một chương trình bên ngoài, hãy đặt `workingDir` rõ ràng nếu lệnh con sử dụng đường dẫn tương đối. Điều này giúp tránh phụ thuộc vào thư mục làm việc mặc định của tiến trình.

## 2. Các thư mục gốc quan trọng trong Gradle

Gradle cung cấp những thuộc tính và API giúp build script xây dựng đường dẫn dựa trên cấu trúc project.

| API/thuộc tính | Ý nghĩa |
|---|---|
| `projectDir` | Thư mục của project hiện tại trong cấu trúc build. |
| `rootProject.projectDir` | Thư mục của root project. |
| `rootDir` | Thư mục gốc của build, thường trùng thư mục project của root project. |
| `layout.projectDirectory` | Đối tượng `Directory` đại diện thư mục project hiện tại. |
| `layout.buildDirectory` | `DirectoryProperty` đại diện thư mục đầu ra của project, mặc định là `build/` bên trong project. |

Trong build nhiều project, mỗi subproject có `projectDir` riêng nhưng cùng chia sẻ `rootDir` của build. Vì thế, cùng một đường dẫn tương đối có thể có ý nghĩa khác nhau tùy bạn gọi từ root project hay subproject.

### Dùng `file()` trong build script

Trong Gradle `Project`, hàm `file()` chuyển một đường dẫn thành `File`. Đường dẫn tương đối được giải quyết từ thư mục của project hiện tại.

```groovy
// Trong build.gradle của project app
def localConfig = file('config/app.yml')
def localSource = file('src/main/java')

println "Config: ${localConfig}"
println "Source: ${localSource}"
```

Nếu build script trên thuộc project `app`, hai đường dẫn tương đối được tính từ thư mục `app`, không phải từ thư mục Terminal nơi người dùng chạy lệnh.

Bạn cũng có thể dùng `layout.projectDirectory.file(...)` hoặc `.dir(...)` để thể hiện rõ rằng đường dẫn thuộc project hiện tại:

```groovy
def configFile = layout.projectDirectory.file('config/app.yml')
def sourceDirectory = layout.projectDirectory.dir('src/main/java')
```

Các API này trả về kiểu `RegularFile` hoặc `Directory`, giúp build script diễn đạt rõ loại tài nguyên đang tham chiếu.

### Tham chiếu đến tệp ở root project

Một subproject đôi khi cần dùng cấu hình chung được lưu tại root project. Khi đó, hãy giải quyết đường dẫn từ root project:

```groovy
// Trong build.gradle của một subproject
def sharedConfig = rootProject.file('config/checkstyle/checkstyle.xml')
```

Hoặc dùng Project Layout:

```groovy
def sharedConfig = rootProject.layout.projectDirectory.file(
    'config/checkstyle/checkstyle.xml'
)
```

Đường dẫn này luôn gắn với root project trong build, bất kể subproject hiện tại nằm ở đâu. Đây là cách phù hợp cho cấu hình dùng chung được quản lý trong cùng repository.

### Đặt đầu ra dưới `build/`

Không nên ghi tệp sinh tự động cạnh mã nguồn. Dùng `layout.buildDirectory` để đầu ra đi theo thư mục build của project:

```groovy
def generatedFile = layout.buildDirectory.file('generated/version.txt')
def reportDirectory = layout.buildDirectory.dir('reports/custom')
```

Với subproject, `layout.buildDirectory` gắn với thư mục build của subproject đó theo cấu hình hiện tại. Nếu project tùy chỉnh build directory, API này sẽ phản ánh giá trị đã cấu hình.

## 3. Dùng Project Layout để khai báo đầu vào và đầu ra

Project Layout API giúp build script mô tả vị trí tệp một cách có cấu trúc. Ví dụ sau đọc một tệp cấu hình thuộc project và ghi bản sao vào thư mục build:

```groovy
def configFile = layout.projectDirectory.file('config/tool.yml')
def copiedFile = layout.buildDirectory.file('generated/tool.yml')

tasks.register('copyToolConfig') {
    group = 'build'
    description = 'Sao chép cấu hình công cụ vào thư mục đầu ra.'

    inputs.file(configFile)
    outputs.file(copiedFile)

    doLast {
        def source = configFile.asFile
        def target = copiedFile.get().asFile

        if (!source.isFile()) {
            throw new GradleException("Không tìm thấy tệp cấu hình: ${source}")
        }

        target.parentFile.mkdirs()
        target.bytes = source.bytes
    }
}
```

Trong ví dụ:

- `layout.projectDirectory.file(...)` tham chiếu tệp đầu vào bên trong project.
- `layout.buildDirectory.file(...)` tạo provider cho tệp đầu ra bên trong build directory.
- `inputs.file(...)` và `outputs.file(...)` giúp Gradle theo dõi dữ liệu task sử dụng và tạo ra.
- `target.parentFile.mkdirs()` tạo thư mục cha nếu chưa tồn tại.
- `target.bytes = source.bytes` sao chép nội dung tệp mà không phải tự nối chuỗi đường dẫn.

Đường dẫn được tạo từ các API của Gradle nên không cần ghép `projectDir + "/" + ...` hoặc tự chọn dấu phân cách theo hệ điều hành.

Với build logic mới, nên ưu tiên các API `Directory`, `RegularFile`, `DirectoryProperty`, `RegularFileProperty` và `Provider` khi phù hợp. Chúng thể hiện ý định và hỗ trợ Gradle quản lý cấu hình, đầu vào và đầu ra tốt hơn so với những chuỗi đường dẫn rời rạc.

## 4. Đường dẫn trong build nhiều project

Giả sử dự án có cấu trúc:

```text
workspace/
├── settings.gradle
├── build.gradle
├── config/
│   └── quality.yml
├── app/
│   ├── build.gradle
│   └── src/
└── library/
    ├── build.gradle
    └── src/
```

Trong `app/build.gradle`, các cách tham chiếu sau có mốc khác nhau:

```groovy
// Tệp thuộc project app
def appConfig = file('config/app.yml')

// Tệp dùng chung nằm tại root project
def sharedQualityConfig = rootProject.file('config/quality.yml')
```

`appConfig` trỏ đến `workspace/app/config/app.yml`. `sharedQualityConfig` trỏ đến `workspace/config/quality.yml`.

Một lỗi thường gặp là dùng `file('../config/quality.yml')` trong nhiều subproject với giả định tất cả module đều nằm ngay dưới root. Điều này trở nên mong manh khi một module được chuyển vào thư mục con sâu hơn hoặc cấu trúc project thay đổi. Nếu tệp thật sự thuộc root project, dùng `rootProject.file(...)` diễn đạt ý định rõ hơn.

### `rootDir` và `projectDir`

Trong một build nhiều project:

- `rootDir` xác định thư mục gốc của build.
- `projectDir` xác định thư mục của project hiện tại.
- `rootProject.projectDir` xác định thư mục của root project.

Không nên nhầm `rootDir` với thư mục hiện tại của Terminal. Người dùng có thể chạy Gradle từ thư mục khác và chỉ định build bằng `-p` hoặc `-c`; thư mục project vẫn được Gradle xác định theo cấu trúc build.

## 5. Đường dẫn trong Maven

Maven cung cấp thuộc tính `${project.basedir}` để tham chiếu thư mục gốc của project hiện tại. Thuộc tính này thường được dùng khi cấu hình plugin, resource hoặc thư mục nguồn tùy chỉnh.

Ví dụ, nếu dự án có tệp cấu hình trong `config/`:

```xml
<build>
    <resources>
        <resource>
            <directory>${project.basedir}/config</directory>
        </resource>
    </resources>
</build>
```

Ở đây, `${project.basedir}` là thư mục chứa `pom.xml` của project tương ứng. Khi repository được checkout ở vị trí khác, Maven vẫn tìm thư mục `config` bên trong project.

### Tùy chỉnh thư mục đầu ra

Thư mục build mặc định của Maven là `${project.basedir}/target`. Có thể cấu hình vị trí khác bằng phần tử `directory`:

```xml
<build>
    <directory>${project.basedir}/build-output</directory>
</build>
```

Các plugin Maven chuẩn thường sử dụng `${project.build.directory}` làm thư mục đầu ra. Khi thay đổi `build.directory`, các plugin tuân theo thuộc tính này sẽ ghi kết quả vào thư mục mới. Plugin tùy chỉnh có thể có cấu hình riêng, do đó cần kiểm tra từng plugin nếu output không di chuyển như dự kiến.

### Đường dẫn resource và plugin

Ví dụ khai báo resource ở vị trí tương đối với project:

```xml
<build>
    <resources>
        <resource>
            <directory>${project.basedir}/src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
    </resources>
</build>
```

Với plugin, hãy ưu tiên các thuộc tính Maven có sẵn như `${project.basedir}`, `${project.build.directory}`, `${project.build.outputDirectory}` hoặc `${project.build.testOutputDirectory}` thay vì ghi cứng đường dẫn của một máy.

Trong Maven multi-module, mỗi module có `project.basedir` riêng. Nếu cần tệp chung nằm ở root aggregator, cần tham chiếu rõ ràng đến vị trí root theo cấu trúc dự án hoặc truyền cấu hình phù hợp. Không nên giả định `${project.basedir}` của module con tự động trỏ về root aggregator.

## 6. Tại sao đường dẫn tuyệt đối làm giảm khả năng di chuyển?

Một dự án được xem là dễ di chuyển khi có thể checkout hoặc sao chép sang một thư mục khác mà không cần sửa các đường dẫn nội bộ. Ví dụ, hai lập trình viên có thể đặt repository ở:

```text
Máy A: C:/dev/java-learning/my-module/
Máy B: D:/projects/java-learning/my-module/
CI:    /home/runner/work/java-learning/my-module/
```

Nếu build script dùng đường dẫn tương đối đến `config/tool.yml`, cả ba môi trường đều có thể tìm tệp theo cấu trúc repository. Nếu build script ghi cứng `C:/dev/java-learning/my-module/config/tool.yml`, hai môi trường còn lại sẽ thất bại.

Đường dẫn tuyệt đối còn có thể gây ra các vấn đề sau:

- **Khó tái sử dụng:** người khác phải sửa build script trước khi chạy.
- **CI thất bại:** runner dùng thư mục checkout, ổ đĩa và tài khoản khác.
- **Build khó tái lập:** kết quả phụ thuộc trạng thái riêng của máy thay vì đầu vào được quản lý.
- **Rò rỉ thông tin môi trường:** đường dẫn có thể tiết lộ tên tài khoản, tên máy hoặc cấu trúc nội bộ.
- **Khó làm việc nhóm:** các thay đổi đường dẫn cá nhân dễ tạo xung đột trong file cấu hình chung.

Đường dẫn tuyệt đối vẫn có chỗ dùng hợp lý khi nó được cung cấp bởi môi trường tại thời điểm chạy, chẳng hạn biến môi trường trỏ đến một SDK cài ngoài repository. Điểm quan trọng là build script không nên tự giả định mọi máy đều có cùng một đường dẫn tuyệt đối.

## 7. Dùng biến môi trường và thuộc tính để nhận cấu hình bên ngoài

Đôi khi dự án cần đọc một công cụ hoặc thư mục dữ liệu nằm ngoài repository. Thay vì ghi cứng vị trí, hãy nhận đường dẫn từ biến môi trường hoặc thuộc tính build.

### Gradle: đọc biến môi trường

Ví dụ, dự án cần một thư mục cài đặt công cụ ngoài:

```groovy
def toolHome = providers.environmentVariable('MY_TOOL_HOME')

tasks.register('showExternalTool') {
    doLast {
        def configuredPath = toolHome.orNull
        if (!configuredPath) {
            throw new GradleException('Hãy thiết lập biến môi trường MY_TOOL_HOME.')
        }

        def toolDirectory = project.file(configuredPath)
        if (!toolDirectory.isDirectory()) {
            throw new GradleException("Thư mục công cụ không tồn tại: ${toolDirectory}")
        }

        println "Tool directory: ${toolDirectory}"
    }
}
```

Biến `MY_TOOL_HOME` được cung cấp bởi môi trường. Mỗi máy có thể cài công cụ ở vị trí khác nhau nhưng vẫn dùng cùng build script. `file(configuredPath)` chuyển đường dẫn thành `File`; nếu giá trị là đường dẫn tuyệt đối thì nó giữ vị trí tuyệt đối, còn đường dẫn tương đối được giải quyết theo project hiện tại.

Có thể truyền thuộc tính Gradle thay cho biến môi trường:

```shell
./gradlew showExternalTool -PtoolHome=/opt/my-tool
```

Trong build script, đọc bằng `providers.gradleProperty('toolHome')`. Với đường dẫn phụ thuộc môi trường máy, hãy ghi rõ trong hướng dẫn dự án cách thiết lập giá trị đó và kiểm tra giá trị trước khi task sử dụng.

### Maven: đọc thuộc tính môi trường

Maven có thể truy cập biến môi trường thông qua cú pháp `${env.VARIABLE_NAME}` trong các cấu hình hỗ trợ interpolation:

```xml
<properties>
    <external.tool.home>${env.MY_TOOL_HOME}</external.tool.home>
</properties>
```

Plugin cần dùng giá trị đó có thể tham chiếu `${external.tool.home}`. Hãy kiểm tra biến đã được đặt và plugin có nhận đúng thuộc tính hay không; không nên giả định một giá trị chưa được cung cấp sẽ tự động có đường dẫn hợp lệ.

### Khi nào dùng biến môi trường, khi nào dùng đường dẫn tương đối?

| Nhu cầu | Cách phù hợp |
|---|---|
| Tệp cấu hình được commit cùng repository | Đường dẫn tương đối từ project hoặc root project. |
| Tệp sinh tự động của build | API thư mục đầu ra như `layout.buildDirectory` hoặc `${project.build.directory}`. |
| SDK/công cụ cài bên ngoài repository | Biến môi trường hoặc thuộc tính được tài liệu hóa. |
| Cache riêng của người dùng | Thư mục home/cache do công cụ hoặc hệ điều hành quản lý. |
| Tệp tạm chỉ dùng trong một task | Thư mục tạm hoặc thư mục build của project. |

Không đưa đường dẫn cá nhân vào cấu hình chung. Nếu cần cấu hình riêng của máy, dùng cơ chế local được ignore hoặc biến môi trường, đồng thời cung cấp mẫu cấu hình và hướng dẫn cho thành viên mới.

## 8. Xây dựng đường dẫn an toàn và độc lập hệ điều hành

### Không tự ghép dấu phân cách

Không nên nối chuỗi theo kiểu:

```groovy
def path = projectDir.toString() + '\\config\\tool.yml'
```

Cách này gắn mã với một kiểu dấu phân cách và dễ tạo đường dẫn sai khi thành phần đã có dấu `/` hoặc `\\` ở cuối. Hãy dùng API của hệ thống tệp:

```groovy
def configFile = layout.projectDirectory.file('config/tool.yml').asFile
```

Trong Java:

```java
import java.nio.file.Path;

Path projectDirectory = Path.of("workspace", "my-app");
Path configFile = projectDirectory.resolve("config").resolve("tool.yml");
```

`Path.resolve(...)` ghép các thành phần theo quy tắc của hệ điều hành. Bạn không cần tự quyết định dấu phân cách thư mục.

Java cũng cung cấp `Path.of(...)`, `Paths.get(...)`, `File` và các API tương tự để làm việc với đường dẫn. Khi viết code Java chạy trên nhiều hệ điều hành, ưu tiên các API này thay vì tự nối chuỗi.

### Dùng dấu `/` trong cấu hình khi phù hợp

Java trên Windows chấp nhận dấu `/` trong nhiều API đường dẫn, và Gradle cũng thường xử lý tốt dạng `config/tool.yml`. Việc dùng `/` trong chuỗi đường dẫn cấu hình giúp ví dụ dễ đọc trên nhiều hệ điều hành:

```groovy
def file = layout.projectDirectory.file('config/tool.yml')
```

Tuy nhiên, với đường dẫn được tạo trong code, vẫn nên dùng `File` hoặc `Path` thay vì dựa vào việc mọi công cụ bên ngoài đều chấp nhận cùng một cú pháp.

### Phân biệt dấu phân cách thư mục và dấu phân cách danh sách

Đường dẫn thư mục dùng dấu phân cách thành phần, ví dụ `/` hoặc `\\`. Classpath trên Java dùng dấu phân cách danh sách khác nhau theo hệ điều hành:

- Windows: dấu chấm phẩy `;`.
- Linux/macOS: dấu hai chấm `:`.

Hai loại dấu phân cách này có mục đích khác nhau. Nếu tự tạo classpath, dùng `File.pathSeparator` trong Java hoặc cơ chế classpath của build tool thay vì ghi cứng `:` hoặc `;`.

### Đường dẫn có khoảng trắng và ký tự Unicode

Một thư mục checkout có thể có khoảng trắng hoặc ký tự Unicode, ví dụ:

```text
C:/Users/Lan Nguyen/Projects/java-app/
/home/lan/du-an-hoc-java/
```

API `File` và `Path` xử lý các ký tự này như một phần của đường dẫn. Khi truyền đường dẫn qua shell, hãy đặt trong dấu ngoặc kép để shell không tách thành nhiều đối số:

PowerShell:

```powershell
Get-Item 'C:\Users\Lan Nguyen\Projects\java-app\config\app.yml'
```

Linux/macOS:

```shell
ls "/home/lan/du-an-hoc-java/config/app.yml"
```

Trong build script, truyền `File` hoặc `Provider<RegularFile>` cho API phù hợp thay vì tự thêm dấu ngoặc kép vào giá trị đường dẫn. Dấu ngoặc kép là cú pháp của shell, không phải ký tự cần lưu trong đường dẫn.

### Chú ý chữ hoa/chữ thường

Một số hệ thống tệp phân biệt chữ hoa và chữ thường, trong khi một số hệ thống khác thì không. Ví dụ `Config/app.yml` và `config/app.yml` có thể được xem là hai đường dẫn khác nhau trên Linux. Hãy dùng chính xác cách viết hoa/thường của tên thư mục và tệp trong repository để build hoạt động nhất quán trên các môi trường.

## 9. Chuẩn hóa và kiểm tra đường dẫn

Khi nhận một đường dẫn từ người dùng, biến môi trường hoặc cấu hình, có thể cần chuẩn hóa và kiểm tra nó trước khi sử dụng.

### Chuẩn hóa đường dẫn bằng Java NIO

```java
import java.nio.file.Path;

Path path = Path.of("config", "..", "config", "app.yml");
Path normalized = path.normalize();

System.out.println(normalized);
```

`normalize()` loại bỏ những thành phần dư thừa theo cú pháp, chẳng hạn `.` và một số cặp `thư-mục/..`. Đây là chuẩn hóa theo cấu trúc đường dẫn, không cần tệp phải tồn tại.

Nếu cần đường dẫn tuyệt đối đã chuẩn hóa:

```java
Path absolute = path.toAbsolutePath().normalize();
```

`toAbsolutePath()` dùng thư mục làm việc hiện tại của tiến trình để biến đường dẫn tương đối thành tuyệt đối. Kết quả vì thế có thể khác giữa các lần chạy nếu working directory khác nhau.

Nếu cần xác định đường dẫn thực trên hệ thống tệp và tệp phải tồn tại:

```java
Path realPath = path.toRealPath();
```

`toRealPath()` có thể giải quyết symbolic link và kiểm tra đường dẫn trên hệ thống tệp; nó thường yêu cầu đường dẫn tồn tại. Ba thao tác `normalize()`, `toAbsolutePath()` và `toRealPath()` có ý nghĩa khác nhau, không nên dùng thay thế cho nhau.

### Kiểm tra tệp trong Gradle

```groovy
def configFile = layout.projectDirectory.file('config/app.yml')

tasks.register('checkLocalConfig') {
    doLast {
        if (!configFile.asFile.isFile()) {
            throw new GradleException("Thiếu cấu hình: ${configFile.asFile}")
        }
        println "Đã tìm thấy: ${configFile.asFile}"
    }
}
```

Thông báo lỗi nên chỉ rõ tệp cần tìm để người chạy biết phải đặt cấu hình ở đâu. Với cấu hình bắt buộc, fail sớm giúp tránh một lỗi khó hiểu xuất hiện sâu hơn trong build.

### Cẩn trọng với `..` và đường dẫn do bên ngoài cung cấp

Đường dẫn như `../../outside/secret.txt` có thể đi ra ngoài thư mục dự án. Nếu task nhận tên tệp hoặc đường dẫn từ đầu vào bên ngoài, đừng mặc định nó luôn nằm trong project. Có thể chuẩn hóa đường dẫn và kiểm tra nó vẫn nằm dưới thư mục gốc được phép trước khi đọc hoặc ghi.

Ví dụ Java:

```java
import java.nio.file.Path;

Path allowedRoot = Path.of("workspace", "generated").toAbsolutePath().normalize();
Path requested = allowedRoot.resolve(userSuppliedName).normalize();

if (!requested.startsWith(allowedRoot)) {
    throw new IllegalArgumentException("Đường dẫn nằm ngoài thư mục được phép.");
}
```

Đây là kiểm tra theo đường dẫn đã chuẩn hóa về mặt cú pháp. Nếu môi trường có symbolic link hoặc thư mục do người khác kiểm soát, cần cân nhắc kiểm tra đường dẫn thực và quyền truy cập phù hợp để tránh đi vòng qua symbolic link.

## 10. Khả năng di chuyển dự án và build tái lập

Một dự án có khả năng di chuyển khi cấu hình build mô tả các đầu vào theo cấu trúc và hợp đồng của dự án, thay vì phụ thuộc vào vị trí riêng trên máy phát triển.

Các nguyên tắc nên áp dụng:

1. Đặt tệp cấu hình dùng chung trong repository nếu chúng thuộc dự án và cần được quản lý phiên bản.
2. Dùng đường dẫn tương đối từ `projectDir`, `rootProject` hoặc `${project.basedir}` cho các tệp thuộc repository.
3. Ghi output vào `layout.buildDirectory` của Gradle hoặc `${project.build.directory}` của Maven.
4. Đưa vị trí công cụ cài ngoài vào biến môi trường hoặc thuộc tính được tài liệu hóa.
5. Tránh sử dụng thư mục home của một lập trình viên làm vị trí bắt buộc cho build chung.
6. Không dựa vào thư mục hiện tại của Terminal trong tác vụ build; đặt working directory rõ ràng khi chạy chương trình bên ngoài.
7. Không tự ghép dấu phân cách đường dẫn; dùng API `File`, `Path` hoặc Project Layout.
8. Kiểm tra chữ hoa/chữ thường và các đường dẫn có khoảng trắng trên môi trường CI.
9. Không ghi tệp sinh tự động vào thư mục nguồn hoặc thư mục dùng chung ngoài project nếu không có lý do rõ ràng.
10. Ghi hướng dẫn thiết lập biến môi trường và cấu hình cục bộ vào tài liệu onboarding của dự án.

### Kiểm tra khả năng di chuyển

Một cách kiểm tra thực tế là checkout cùng commit vào một thư mục khác, có thể có khoảng trắng trong tên, rồi chạy lại build. Ví dụ:

```text
Vị trí ban đầu: C:/dev/java-app/
Vị trí thử:     D:/temporary/build test/java-app/
```

Trên CI, build thường chạy trong một thư mục checkout do runner quyết định. Nếu build chỉ thành công tại một đường dẫn cố định, hãy tìm các chuỗi tuyệt đối trong build script, file cấu hình và script hỗ trợ.

Bạn có thể tìm những dấu hiệu cần xem lại bằng tìm kiếm văn bản trong repository, nhưng không phải mọi đường dẫn tuyệt đối đều sai: có thể có URL, ví dụ tài liệu hoặc đường dẫn chỉ dùng trong test. Hãy xác định ngữ cảnh trước khi thay đổi.

## 11. Một số lỗi thường gặp liên quan đến đường dẫn

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Build báo không tìm thấy tệp cấu hình | Đường dẫn tương đối được tính từ một project khác hoặc tệp chưa có trong checkout. | Xác định mốc của đường dẫn; dùng `projectDir`, `rootProject` hoặc `${project.basedir}` đúng mục đích. |
| Chạy được trên máy cá nhân nhưng CI thất bại | Build script ghi cứng đường dẫn tuyệt đối hoặc dựa vào biến môi trường chưa cấu hình trên CI. | Dùng đường dẫn nội bộ tương đối hoặc cấu hình biến môi trường rõ ràng trong CI. |
| Task ghi đầu ra vào thư mục không mong muốn | Đường dẫn tương đối được giải quyết từ project khác hoặc working directory của tiến trình con khác dự kiến. | Dùng Project Layout cho output và đặt `workingDir` rõ ràng cho tiến trình con. |
| Lỗi chỉ xuất hiện trên Linux | Sai chữ hoa/thường trong tên tệp hoặc dùng dấu phân cách không phù hợp trong script. | Kiểm tra tên chính xác và dùng API đường dẫn thay vì nối chuỗi. |
| Đường dẫn chứa khoảng trắng làm lệnh thất bại | Shell tách đường dẫn thành nhiều đối số. | Đặt đối số đường dẫn trong dấu ngoặc kép khi gọi qua shell. |
| Đường dẫn có `..` truy cập nhầm vị trí | Mốc đường dẫn chưa được xác định hoặc cấu trúc thư mục thay đổi. | Chuẩn hóa và kiểm tra đường dẫn; ưu tiên tham chiếu root/project rõ ràng. |
| Dùng `~` nhưng không tìm thấy thư mục home | `~` thường được shell mở rộng, không phải cú pháp tự động của `File` hoặc Gradle. | Dùng `user.home` hoặc API cấu hình phù hợp. |

### Kiểm tra thư mục hiện tại trong shell

Khi một lệnh Terminal không tìm thấy tệp, hãy kiểm tra working directory:

PowerShell:

```powershell
Get-Location
Resolve-Path '.\config\app.yml'
Test-Path '.\config\app.yml'
```

Linux/macOS:

```shell
pwd
realpath config/app.yml
test -f config/app.yml && echo "Found"
```

Những lệnh này giúp kiểm tra đường dẫn mà shell đang sử dụng. Chúng không thay đổi quy tắc giải quyết đường dẫn bên trong Gradle hoặc Maven.

## 12. Bài thực hành

Thực hành với một dự án Java có Gradle hoặc Maven:

1. Tạo một tệp `config/tool.yml` trong repository.
2. Trong Gradle, tham chiếu tệp bằng `layout.projectDirectory.file('config/tool.yml')`; nếu dùng Maven, dùng `${project.basedir}/config/tool.yml` trong cấu hình plugin phù hợp.
3. Tạo một task sinh tệp vào `build/generated/` bằng `layout.buildDirectory`.
4. Chuyển repository sang một thư mục checkout khác và chạy lại tác vụ. Xác nhận cấu hình nội bộ vẫn được tìm thấy.
5. Nếu dự án có nhiều module, tham chiếu một tệp trong module bằng `file(...)`, sau đó tham chiếu cấu hình chung bằng `rootProject.file(...)`. Ghi lại hai đường dẫn được giải quyết.
6. Tạo một đường dẫn tuyệt đối đến một vị trí chỉ có trên máy của bạn, quan sát vì sao nó không phù hợp cho cấu hình chung, rồi thay bằng biến môi trường hoặc đường dẫn tương đối.
7. Đặt repository trong một đường dẫn có khoảng trắng và chạy build. Nếu có script shell, kiểm tra cách truyền đối số đường dẫn.
8. Viết một ví dụ Java dùng `Path.resolve()` và `normalize()` để xây dựng đường dẫn từ thư mục gốc dự án.
9. Thử một đường dẫn có `..` và kiểm tra nó có nằm trong thư mục gốc được phép hay không.
10. Ghi lại những cấu hình môi trường cần thiết để một thành viên mới hoặc CI có thể chạy build mà không sửa build script.

Sau bài thực hành, bạn cần giải thích được mốc giải quyết đường dẫn tương đối trong shell, Gradle và Maven; phân biệt `projectDir`, `rootDir`, `layout.buildDirectory` và `${project.basedir}`; biết khi nào nên dùng biến môi trường; và xây dựng được cấu hình không phụ thuộc vào đường dẫn tuyệt đối của một máy cụ thể. Đây là nền tảng để dự án Java có thể được checkout, build và triển khai ổn định trên nhiều máy cũng như nhiều hệ điều hành.
