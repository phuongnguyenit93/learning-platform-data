# Đóng gói script khởi động, cấu hình mẫu và tài liệu đi kèm

## 1. Thành phần của một gói phát hành

Một ứng dụng Java có thể chạy tốt trên máy phát triển vì IDE đã cấu hình classpath, biến môi trường và thư mục làm việc. Người nhận artifact phát hành cần biết phải chạy lệnh nào, dùng JDK nào, đặt cấu hình ở đâu và tìm hướng dẫn tại vị trí nào.

Một distribution thường gồm:

- **Ứng dụng và dependency runtime**: JAR chính cùng các JAR cần thiết khi chạy.
- **Script khởi động**: cung cấp cách chạy thống nhất trên những hệ điều hành được hỗ trợ.
- **Cấu hình mẫu**: liệt kê các tùy chọn mà người triển khai cần thiết lập.
- **Tài liệu**: hướng dẫn cài đặt, cấu hình, khởi động, nâng cấp và xử lý lỗi.
- **Thông tin pháp lý và phiên bản**: license, notice của thư viện bên thứ ba, changelog và metadata phát hành khi cần.

Apache Ant có thể tập hợp các thành phần này thành một thư mục phân phối rồi tạo archive ZIP hoặc TAR. Người nhận có thể giải nén gói và khởi chạy ứng dụng mà không cần biết source tree hoặc cách build nội bộ.

## 2. Thiết kế cấu trúc thư mục phát hành

Một layout rõ ràng giúp script và tài liệu tham chiếu các thành phần bằng đường dẫn tương đối. Ví dụ:

```text
myapp-1.0.0/
├── bin/
│   ├── run.sh
│   └── run.bat
├── conf/
│   └── app.properties.example
├── lib/
│   ├── app.jar
│   └── gson-2.11.0.jar
├── docs/
│   ├── INSTALL.md
│   ├── CONFIGURATION.md
│   └── CHANGELOG.md
├── LICENSE
├── NOTICE
└── README.md
```

| Thành phần | Vai trò |
|---|---|
| `bin/` | Script chạy ứng dụng hoặc tiện ích quản trị |
| `conf/` | Cấu hình bên ngoài JAR |
| `lib/` | JAR ứng dụng và dependency runtime |
| `docs/` | Hướng dẫn cài đặt, cấu hình và nâng cấp |
| `LICENSE` | Điều khoản cấp phép của dự án |
| `NOTICE` | Thông báo bản quyền hoặc ghi nhận cần phân phối |
| `README.md` | Giới thiệu nhanh và liên kết tới hướng dẫn chi tiết |

Không phải dự án nào cũng cần tất cả các tệp trên. Chỉ đưa những tài liệu và metadata thực sự áp dụng cho sản phẩm. Nếu ứng dụng không có dependency ngoài, thư mục `lib/` có thể chỉ chứa JAR chính.

Nên phân biệt source tree với distribution tree. Các thư mục như `src/main/java`, `build/classes` và file cấu hình của công cụ build là đầu vào hoặc sản phẩm trung gian. Người cài đặt không cần toàn bộ source tree nếu sản phẩm chỉ được phân phối dưới dạng binary.

## 3. Chuẩn bị các thành phần đầu vào trong repository

Có thể lưu các file phân phối do nhóm duy trì trong các thư mục riêng:

```text
project/
├── build.xml
├── src/
│   └── main/
│       ├── java/
│       └── resources/
├── lib/
│   └── gson-2.11.0.jar
├── dist-src/
│   └── bin/
│       ├── run.sh
│       └── run.bat
├── conf/
│   └── app.properties.example
├── docs/
│   ├── INSTALL.md
│   ├── CONFIGURATION.md
│   └── CHANGELOG.md
├── LICENSE
├── NOTICE
└── README.md
```

Các file trong `dist-src/`, `conf/` và `docs/` là đầu vào để Ant copy vào distribution. Chúng không cần nằm trong JAR ứng dụng.

Tách cấu hình mẫu khỏi cấu hình triển khai thực tế. Repository nên chứa `app.properties.example` với giá trị minh họa an toàn. Người cài đặt sao chép nó thành `app.properties` rồi chỉnh theo môi trường. File chứa mật khẩu, token, khóa riêng hoặc thông tin nội bộ không nên được đưa vào gói mẫu hay commit vào source control.

## 4. Script khởi động trên Linux và macOS

Script POSIX shell nên xác định vị trí của chính nó trước khi tìm JAR và file cấu hình. Nhờ vậy, người dùng có thể gọi script từ thư mục bất kỳ mà không phụ thuộc current working directory.

Ví dụ `dist-src/bin/run.sh`:

```sh
#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_HOME=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ -n "${JAVA_HOME:-}" ]; then
    JAVA="$JAVA_HOME/bin/java"
else
    JAVA=java
fi

if [ ! -x "$JAVA" ] && [ "$JAVA" != "java" ]; then
    echo "Java executable not found: $JAVA" >&2
    exit 1
fi

APP_JAR="$APP_HOME/lib/app.jar"
APP_CONFIG="$APP_HOME/conf/app.properties"
SAMPLE_CONFIG="$APP_HOME/conf/app.properties.example"

if [ ! -f "$APP_JAR" ]; then
    echo "Application JAR not found: $APP_JAR" >&2
    exit 1
fi

if [ ! -f "$APP_CONFIG" ]; then
    echo "Configuration file not found: $APP_CONFIG" >&2
    echo "Copy $SAMPLE_CONFIG to $APP_CONFIG and edit it first." >&2
    exit 1
fi

exec "$JAVA" \
    "-Dapp.config=$APP_CONFIG" \
    -jar "$APP_JAR" "$@"
```

Một số điểm cần chú ý:

- `SCRIPT_DIR` là thư mục `bin/`; `APP_HOME` là thư mục gốc của distribution.
- `JAVA_HOME` cho phép chọn JDK cụ thể. Nếu không đặt, script dùng lệnh `java` tìm thấy qua `PATH`.
- `exec` thay tiến trình shell bằng JVM, nhờ đó mã thoát và tín hiệu của ứng dụng được truyền trực tiếp hơn.
- `"$@"` giữ nguyên từng đối số mà người dùng truyền cho script, kể cả đối số có khoảng trắng.
- Script kiểm tra JAR và cấu hình trước khi khởi chạy để đưa ra thông báo dễ hiểu.

Đánh dấu script có quyền thực thi trước khi chạy hoặc đóng gói trên Unix:

```bash
chmod 755 bin/run.sh
./bin/run.sh
```

Nếu script được lưu trong Git, có thể commit executable bit để checkout giữ đúng quyền. Khi tạo archive trên Windows, cần kiểm tra riêng permission trong archive; phần mở rộng `.sh` không tự làm file executable trên Linux.

Nếu muốn truyền thêm JVM options, hãy thiết kế cách cấu hình có quy tắc rõ ràng. Không dùng `eval` để thực thi nội dung biến môi trường. Chuỗi `JAVA_OPTS` có dấu cách và ký tự shell có thể được phân tích khác nhau giữa các shell; nếu cần hỗ trợ options tùy ý, hãy định nghĩa cú pháp và cách parse có kiểm soát hoặc dùng file JVM arguments theo yêu cầu ứng dụng.

## 5. Script khởi động trên Windows

Windows có thể dùng Command Prompt script với phần mở rộng `.bat`. Ví dụ `dist-src/bin/run.bat`:

```bat
@echo off
setlocal

set "APP_HOME=%~dp0.."
for %%I in ("%APP_HOME%") do set "APP_HOME=%%~fI"

if defined JAVA_HOME (
    set "JAVA=%JAVA_HOME%\bin\java.exe"
) else (
    set "JAVA=java"
)

set "APP_JAR=%APP_HOME%\lib\app.jar"
set "APP_CONFIG=%APP_HOME%\conf\app.properties"

if not exist "%APP_JAR%" (
    echo Application JAR not found: "%APP_JAR%" 1>&2
    exit /b 1
)

if not exist "%APP_CONFIG%" (
    echo Configuration file not found: "%APP_CONFIG%" 1>&2
    echo Copy app.properties.example to app.properties and edit it first. 1>&2
    exit /b 1
)

"%JAVA%" "-Dapp.config=%APP_CONFIG%" -jar "%APP_JAR%" %*
exit /b %ERRORLEVEL%
```

`%~dp0` là thư mục chứa file batch. Từ đó, script xác định thư mục gốc của distribution. `setlocal` giới hạn các biến môi trường trong script, tránh để lại thay đổi trong cửa sổ Command Prompt gọi nó.

`%*` chuyển các đối số nhận được tới ứng dụng. Nếu ứng dụng cần nhận đối số có quy tắc quoting phức tạp, hãy kiểm thử với Command Prompt và cách gọi thực tế trên Windows. Không tự nối các giá trị người dùng thành một chuỗi lệnh khác.

Hai script nên cung cấp cùng hành vi cơ bản: chọn Java, xác định thư mục ứng dụng, kiểm tra đầu vào bắt buộc và khởi chạy cùng JAR với cùng file cấu hình. Khác biệt về dấu phân cách đường dẫn và cú pháp shell được giữ trong từng script.

## 6. Cấu hình mẫu bên ngoài ứng dụng

Ví dụ `conf/app.properties.example`:

```properties
# Application configuration template.
# Copy this file to app.properties and adjust values for your environment.

app.name=My Application
app.environment=development
server.host=127.0.0.1
server.port=8080
logging.level=INFO
data.directory=../data
```

Ứng dụng có thể đọc đường dẫn file cấu hình từ system property `app.config`, được script truyền bằng tùy chọn `-Dapp.config=...`. Trong Java, có thể đọc system property và nạp file như sau:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class AppConfig {
    private AppConfig() {
    }

    public static Properties load() throws Exception {
        String configuredPath = System.getProperty("app.config");
        if (configuredPath == null || configuredPath.isBlank()) {
            throw new IllegalStateException(
                "Missing required system property: app.config");
        }

        Path path = Path.of(configuredPath);
        if (!Files.isRegularFile(path)) {
            throw new IllegalStateException(
                "Configuration file does not exist: " + path);
        }

        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(path)) {
            properties.load(input);
        }
        return properties;
    }
}
```

Ví dụ này dùng `Properties.load(InputStream)`, vốn đọc định dạng Java Properties truyền thống với quy tắc encoding ISO-8859-1 và escape Unicode. Nếu file cần lưu tiếng Việt hoặc ký tự Unicode trực tiếp, hãy chọn cách đọc UTF-8 tường minh, chẳng hạn `Files.newBufferedReader(path, StandardCharsets.UTF_8)` kết hợp `Properties.load(Reader)`, và ghi rõ encoding đó trong tài liệu cấu hình.

Cấu hình bên ngoài JAR cho phép thay đổi port, log level hoặc đường dẫn dữ liệu mà không phải build lại ứng dụng. Khi nâng cấp, giữ file `app.properties` hiện tại và đối chiếu với file mẫu của phiên bản mới để bổ sung khóa mới. Script khởi động không nên tự ghi đè file cấu hình đã được người triển khai chỉnh sửa.

## 7. Viết tài liệu đi kèm

Tài liệu phát hành nên hướng dẫn người dùng theo trình tự công việc:

- **README.md** giới thiệu sản phẩm, phiên bản, chức năng chính, JDK yêu cầu và cách bắt đầu nhanh. README liên kết tới hướng dẫn chi tiết.
- **INSTALL.md** mô tả cách giải nén gói, cấu trúc thư mục, quyền chạy script, cách chọn Java và bước tạo cấu hình thực tế.
- **CONFIGURATION.md** liệt kê từng khóa trong `app.properties`, ý nghĩa, kiểu giá trị, giá trị mặc định và phạm vi hợp lệ.
- **CHANGELOG.md** ghi lại thay đổi theo phiên bản, đặc biệt các thay đổi cấu hình ảnh hưởng tới nâng cấp.

Một phần hướng dẫn cài đặt mẫu:

```markdown
# Cài đặt My Application

## Yêu cầu

- JDK tương thích với phiên bản phát hành.
- Quyền đọc thư mục cài đặt và quyền ghi vào các thư mục dữ liệu mà ứng dụng sử dụng.

## Chuẩn bị

1. Sao chép file cấu hình mẫu conf/app.properties.example thành conf/app.properties.
2. Chỉnh các giá trị trong conf/app.properties.
3. Kiểm tra Java bằng lệnh java -version.

## Khởi chạy

Trên Linux hoặc macOS:

    chmod 755 bin/run.sh
    ./bin/run.sh

Trên Windows:

    bin\run.bat

## Nâng cấp

- Sao lưu file cấu hình và dữ liệu trước khi thay phiên bản.
- Giữ lại conf/app.properties.
- Đọc CHANGELOG và so sánh cấu hình mẫu của phiên bản mới.
- Chỉ bổ sung hoặc thay đổi khóa cấu hình theo hướng dẫn.
```

Tài liệu cấu hình nên có bảng dạng:

| Khóa | Ý nghĩa | Ví dụ | Ghi chú |
|---|---|---|---|
| `app.environment` | Môi trường chạy | `production` | Chọn theo môi trường |
| `server.host` | Địa chỉ bind | `0.0.0.0` | Chỉ mở trên interface cần thiết |
| `server.port` | Cổng dịch vụ | `8080` | Phải chưa bị tiến trình khác sử dụng |
| `logging.level` | Mức log | `INFO` | Chọn theo chính sách vận hành |
| `data.directory` | Thư mục dữ liệu | `../data` | Cần quyền ghi phù hợp |

Các giá trị trong bảng là ví dụ. Tài liệu thật phải khớp với những khóa mà ứng dụng thực sự đọc; không đưa khóa minh họa vào cấu hình sản phẩm nếu code không hỗ trợ.

## 8. Đóng gói distribution bằng Ant

Ant có thể tạo thư mục phân phối bằng các task `mkdir`, `copy`, `fileset`, `chmod` và `zip`. Ví dụ dưới đây giả định target `jar` đã tạo `build/lib/app.jar`, JAR phụ thuộc nằm trong `lib/`, còn script và tài liệu có trong source tree như cấu trúc đã nêu.

```xml
<project name="myapp" default="package-release" basedir=".">
    <property name="app.version" value="1.0.0"/>
    <property name="build.dir" value="build"/>
    <property name="dist.dir"
              value="${build.dir}/distribution/myapp-${app.version}"/>
    <property name="release.dir" value="${build.dir}/releases"/>

    <!-- Target compile và jar của dự án được khai báo ở phần build tương ứng. -->

    <target name="stage-distribution" depends="jar">
        <delete dir="${dist.dir}"/>

        <mkdir dir="${dist.dir}/bin"/>
        <mkdir dir="${dist.dir}/conf"/>
        <mkdir dir="${dist.dir}/lib"/>
        <mkdir dir="${dist.dir}/docs"/>

        <copy file="${build.dir}/lib/app.jar"
              todir="${dist.dir}/lib"/>

        <copy file="lib/gson-2.11.0.jar"
              todir="${dist.dir}/lib"/>

        <copy todir="${dist.dir}/bin">
            <fileset dir="dist-src/bin"/>
        </copy>

        <copy file="conf/app.properties.example"
              todir="${dist.dir}/conf"/>

        <copy todir="${dist.dir}/docs">
            <fileset dir="docs"/>
        </copy>

        <copy file="README.md" todir="${dist.dir}"/>
        <copy file="LICENSE" todir="${dist.dir}"/>
        <copy file="NOTICE" todir="${dist.dir}"/>
    </target>

    <condition property="is.unix">
        <os family="unix"/>
    </condition>

    <target name="set-launcher-permissions"
            depends="stage-distribution"
            if="is.unix">
        <chmod file="${dist.dir}/bin/run.sh" perm="755"/>
    </target>

    <target name="package-release"
            depends="set-launcher-permissions">
        <mkdir dir="${release.dir}"/>

        <zip destfile="${release.dir}/myapp-${app.version}.zip">
            <zipfileset dir="${dist.dir}"
                        prefix="myapp-${app.version}"/>
        </zip>
    </target>
</project>
```

Các target thực hiện những việc sau:

1. `stage-distribution` tạo lại thư mục staging do build quản lý và copy các thành phần vào đúng vị trí.
2. `set-launcher-permissions` chạy trên hệ Unix để đặt quyền thực thi cho `run.sh`. Trên hệ điều hành khác, target được bỏ qua.
3. `package-release` tạo ZIP có thư mục gốc mang tên sản phẩm và phiên bản.

Task `delete` trong ví dụ chỉ xóa thư mục staging nằm dưới `build/`, vốn là sản phẩm trung gian được tạo lại. Không đặt cấu hình triển khai thực tế hoặc dữ liệu người dùng trong thư mục staging này. Nếu dự án dùng thư mục distribution có dữ liệu do người dùng quản lý, hãy dùng thư mục build mới hoặc chỉ dọn các file do Ant sở hữu.

Các đường dẫn trong ví dụ tương đối với `basedir` của project. Nếu dự án có nhiều module hoặc chạy Ant từ thư mục khác, hãy khai báo rõ đường dẫn gốc và tránh phụ thuộc vào current working directory của shell.

Nếu cần phát hành cả ZIP và TAR.GZ, có thể dùng task `tar` và `gzip` của Ant. Hãy kiểm tra quyền executable và cấu trúc archive sau khi tạo, đặc biệt khi artifact được build trên Windows nhưng cài đặt trên Linux.

## 9. Giữ script, cấu hình và JAR nhất quán

Một lỗi triển khai phổ biến là script trỏ tới một đường dẫn, trong khi Ant lại copy JAR hoặc cấu hình sang vị trí khác. Hãy thống nhất layout rồi dùng nó trong build file, script và tài liệu.

| Thành phần | Đường dẫn trong distribution |
|---|---|
| Script Linux/macOS | `bin/run.sh` |
| Script Windows | `bin/run.bat` |
| JAR chính | `lib/app.jar` |
| Dependency | `lib/gson-2.11.0.jar` |
| Cấu hình thực tế | `conf/app.properties` |
| Cấu hình mẫu | `conf/app.properties.example` |

Nếu manifest của JAR khai báo dependency theo đường dẫn tương đối, đường dẫn đó được tính từ vị trí JAR chính. Với layout trên, manifest của `lib/app.jar` có thể tham chiếu `gson-2.11.0.jar` vì hai file cùng nằm trong `lib/`.

Script nên tính `APP_HOME` từ vị trí script và truyền đường dẫn cấu hình tuyệt đối vào JVM. Cách này tránh việc chạy script từ thư mục khác làm ứng dụng tìm nhầm file cấu hình.

Không nên dựa vào biến môi trường chỉ có trên máy build để tìm dependency runtime. Mọi JAR cần thiết phải nằm trong distribution hoặc được khai báo rõ là do môi trường triển khai cung cấp.

## 10. Bảo toàn cấu hình và dữ liệu khi nâng cấp

Cấu hình thực tế thường khác nhau giữa development, staging và production. Vì vậy, cấu hình triển khai cần được quản lý độc lập với artifact binary.

Khi phát hành phiên bản mới:

1. Giữ bản sao lưu của cấu hình và dữ liệu đang dùng.
2. Giải nén artifact mới vào thư mục phiên bản mới hoặc thư mục staging.
3. Đối chiếu `app.properties.example` mới với `app.properties` hiện tại.
4. Bổ sung khóa mới theo hướng dẫn và xác minh giá trị.
5. Chạy kiểm tra trước khi chuyển lưu lượng hoặc thay phiên bản đang hoạt động.
6. Giữ đường lui về artifact và cấu hình phiên bản trước theo chính sách vận hành.

Không để target đóng gói tự động xóa hoặc ghi đè cấu hình thực tế. Target staging có thể tạo thư mục mới sạch, nhưng thao tác cài đặt vào môi trường đang chạy cần có quy trình riêng và kiểm soát rõ file nào được thay thế.

Nếu cấu hình có thay đổi không tương thích, ghi rõ trong changelog và hướng dẫn nâng cấp. Nếu có khóa đã bị loại bỏ, nêu cách chuyển đổi thay vì âm thầm bỏ qua.

## 11. Kiểm tra gói phát hành sau khi tạo

Sau khi Ant tạo archive, hãy xác nhận các thành phần bắt buộc có mặt:

```bash
jar tf build/distribution/myapp-1.0.0/lib/app.jar
unzip -l build/releases/myapp-1.0.0.zip
```

Có thể kiểm tra nội dung manifest của JAR:

```bash
unzip -p build/distribution/myapp-1.0.0/lib/app.jar META-INF/MANIFEST.MF
```

Kiểm tra thêm:

- Cả `run.sh` và `run.bat` có trong archive.
- Script tham chiếu đúng `lib/app.jar` và `conf/app.properties`.
- File cấu hình mẫu có trong `conf/`.
- README, hướng dẫn cài đặt, cấu hình, changelog và thông tin license có mặt theo yêu cầu.
- Mọi dependency runtime đều được copy và đường dẫn khớp với manifest.
- `run.sh` giữ executable permission trong archive khi phát hành cho Unix.
- Archive có thư mục gốc và tên phiên bản đúng quy ước.
- Không có file cấu hình thực tế, secret, log, cache hoặc file tạm của máy build.

Kiểm tra cuối cùng nên được thực hiện bằng chính artifact đã giải nén vào một thư mục sạch, không dựa vào source tree. Thử khởi chạy bằng script tương ứng trên hệ điều hành được hỗ trợ. Điều này phát hiện dependency vô tình được cung cấp bởi IDE hoặc classpath cục bộ.

## 12. Lỗi thường gặp

### Script chỉ chạy khi gọi từ thư mục dự án

Script đang dùng đường dẫn tương đối theo current working directory. Hãy xác định thư mục script bằng `%~dp0` trên Windows hoặc `dirname "$0"` trên Unix rồi suy ra `APP_HOME`.

### Không tìm thấy Java

Kiểm tra `JAVA_HOME`, `PATH` và phiên bản JDK được hỗ trợ. Script cần báo lỗi rõ ràng nếu `JAVA_HOME` trỏ tới vị trí không tồn tại.

### Không tìm thấy file cấu hình

Đảm bảo người cài đặt đã copy file mẫu thành file cấu hình thực tế. Ghi rõ bước này trong INSTALL và không để script tự ghi đè cấu hình đã tồn tại.

### Chạy được trên máy phát triển nhưng thiếu thư viện khi phát hành

Classpath IDE hoặc thư mục local có thể đang cung cấp dependency. Kiểm tra manifest, thư mục `lib/` và thử chạy artifact sau khi giải nén vào một thư mục sạch.

### Script Unix không có quyền thực thi

Đặt executable bit trong Git hoặc dùng `chmod 755` khi staging. Xác nhận permission của file trong archive trên môi trường Unix.

### File cấu hình bị sai encoding

Thống nhất encoding trong tài liệu và code đọc cấu hình. Với Java Properties, phân biệt `Properties.load(InputStream)` và `Properties.load(Reader)` để tránh lỗi ký tự Unicode.

### Nâng cấp làm mất cấu hình

Không copy file mẫu lên file cấu hình thực tế trong mỗi lần phát hành. Chỉ phân phối file `.example`; hướng dẫn người vận hành sao lưu và hợp nhất thay đổi.

### Archive chứa file thừa hoặc thiếu tài liệu

Dùng danh sách đầu vào rõ ràng cho distribution và kiểm tra nội dung archive. Tránh copy toàn bộ repository vào gói phát hành bằng một fileset quá rộng.

## 13. Nguyên tắc duy trì gói phát hành

- Giữ layout distribution ổn định giữa các phiên bản để script và hướng dẫn không phải thay đổi vô cớ.
- Đóng gói JAR, dependency runtime, launcher, cấu hình mẫu và tài liệu như các thành phần của cùng một artifact.
- Tính đường dẫn từ vị trí script thay vì giả định người dùng đang đứng ở thư mục cài đặt.
- Đặt quyền thực thi cho script Unix và kiểm tra quyền đó trong archive.
- Tách cấu hình mẫu khỏi cấu hình thực tế; không đóng gói secret.
- Ghi rõ JDK tối thiểu, lệnh khởi chạy, file cấu hình và quy trình nâng cấp.
- Giữ license và thông báo của dependency theo yêu cầu phân phối.
- Tạo archive từ thư mục staging sạch và kiểm tra bằng cách giải nén, chạy thử.
- Dùng cùng một target Ant để tạo artifact có thể tái lập cho developer và CI.

Một gói phát hành dễ sử dụng khi người nhận có đủ JAR, dependency, script, cấu hình mẫu và tài liệu trong một layout nhất quán. Ant đảm nhận việc dựng layout và tạo archive; script xác định Java, đường dẫn ứng dụng và cấu hình; tài liệu giải thích cách cài đặt và nâng cấp. Khi các phần này được quản lý cùng nhau, artifact có thể được kiểm tra và triển khai độc lập với môi trường phát triển.

