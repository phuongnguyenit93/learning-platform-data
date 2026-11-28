# Kiểm tra đường dẫn làm việc và vị trí cấu hình ghi được sau cài đặt

## 1. Vì sao ứng dụng không nên ghi file vào thư mục cài đặt?

Khi chạy từ IDE hoặc terminal, ứng dụng Java thường có thể tạo file ngay trong thư mục project. Sau khi đóng gói bằng `jpackage` và cài đặt cho người dùng, thư mục ứng dụng có thể nằm trong `Program Files` trên Windows, `/opt` trên Linux hoặc `/Applications` trên macOS. Những vị trí này thường do installer hoặc quản trị viên quản lý và người dùng chạy ứng dụng không có quyền ghi.

Nếu ứng dụng lưu cấu hình, log, cache hoặc dữ liệu người dùng cạnh file JAR/runtime, các tình huống sau có thể xảy ra:

- Ứng dụng chạy được khi phát triển nhưng lỗi `AccessDeniedException` sau cài đặt.
- Cập nhật hoặc gỡ cài đặt làm mất file cấu hình người dùng.
- Hai tài khoản dùng chung một file cấu hình, ghi đè lựa chọn của nhau.
- Shortcut, service hoặc tác vụ nền khởi chạy với working directory khác dự kiến.
- Ứng dụng vô tình ghi đè resource đi kèm bản cài đặt.

Hãy tách rõ ba loại vị trí:

1. **Working directory:** thư mục hiện hành của tiến trình, nơi đường dẫn tương đối được phân giải.
2. **Application/install directory:** nơi chứa launcher, runtime, JAR và resource bất biến được cài cùng ứng dụng.
3. **User data/config directory:** vị trí riêng có thể ghi cho tài khoản đang chạy ứng dụng.

Đường dẫn của ba loại này có thể khác nhau. Một ứng dụng đóng gói tốt không phụ thuộc vào việc người dùng khởi chạy nó từ thư mục nào.

## 2. Working directory không phải thư mục cài đặt

Java cung cấp system property `user.dir` để biểu thị working directory của JVM:

~~~java
import java.nio.file.Path;

public class WorkingDirectoryProbe {
    public static void main(String[] args) {
        System.out.println("user.dir = " + System.getProperty("user.dir"));
        System.out.println("current = " + Path.of("").toAbsolutePath());
    }
}
~~~

Hai giá trị trên thường tương ứng với thư mục hiện hành khi JVM được khởi chạy. Đường dẫn tương đối như `Path.of("config/app.properties")` được phân giải dựa trên working directory, không tự động dựa trên vị trí JAR hay thư mục cài đặt.

Working directory có thể thay đổi theo cách khởi chạy:

- Terminal: thường là thư mục mà người dùng đang đứng khi gọi lệnh.
- IDE: thường được cấu hình trong Run Configuration.
- Shortcut/launcher: phụ thuộc launcher và môi trường desktop.
- Windows Task Scheduler, systemd hoặc service manager: phụ thuộc cấu hình của tác vụ/service.
- Container: phụ thuộc `WORKDIR` hoặc thiết lập của runtime container.

Không dùng `user.dir` làm vị trí lưu cấu hình lâu dài. Nó hữu ích để hiển thị thông tin chẩn đoán, xử lý file đầu vào do người dùng chỉ định hoặc xác định cách phân giải đường dẫn tương đối theo hợp đồng của lệnh.

## 3. Đường dẫn tương đối và tuyệt đối trong Java NIO

Một đường dẫn tương đối không có gốc độc lập. Java phân giải nó theo thư mục hiện hành:

~~~java
import java.nio.file.Path;

public class PathResolution {
    public static void main(String[] args) {
        Path relative = Path.of("data", "orders.csv");
        Path absolute = relative.toAbsolutePath().normalize();

        System.out.println("Relative: " + relative);
        System.out.println("Resolved: " + absolute);
        System.out.println("Working directory: "
                + Path.of("").toAbsolutePath().normalize());
    }
}
~~~

`toAbsolutePath()` làm rõ đường dẫn đang được phân giải ở đâu; `normalize()` loại bỏ các thành phần dư thừa như `.` và `..` về mặt cú pháp. Nó không bảo đảm file tồn tại, có quyền truy cập hoặc đã được canonicalize qua symbolic link.

Nếu file là đầu vào do người dùng chọn, có thể giữ nguyên đường dẫn đã chọn hoặc chuyển thành absolute path trước khi đưa vào tác vụ nền. Nếu ứng dụng tự tạo file cấu hình, hãy xây đường dẫn từ user config directory đã xác định, không nối thêm vào working directory.

## 4. Thư mục cài đặt do jpackage tạo

`jpackage` tạo application image gồm launcher, file ứng dụng và Java runtime. Cấu trúc chi tiết thay đổi theo nền tảng:

| Nền tảng | Vị trí cài đặt mặc định thường gặp | Thành phần trong application image |
| --- | --- | --- |
| Windows | `C:\Program Files\<application>`; cài per-user có thể nằm dưới `AppData\Local` | Launcher `.exe`, thư mục `app` và `runtime` |
| Linux | `/opt/<application>` | Thư mục `bin`, `lib/app` và `lib/runtime` |
| macOS | `/Applications/<application>.app` | App bundle với `Contents/MacOS`, `Contents/app` và `Contents/runtime` |

Đây là bố cục tham khảo; đường dẫn thực tế phụ thuộc loại installer, tùy chọn cài đặt và cấu hình của hệ điều hành. Người dùng hoặc quản trị viên có thể chọn vị trí khác.

Thư mục cài đặt chủ yếu chứa file do nhà phát hành quản lý:

- Launcher và runtime image.
- JAR/module của ứng dụng.
- Resource mặc định chỉ đọc.
- Native library và tài nguyên cần thiết để chạy ứng dụng.

Không coi thư mục cài đặt là nơi lưu cấu hình hoặc dữ liệu thay đổi trong quá trình sử dụng. Trên Windows, thư mục dưới `Program Files` thường yêu cầu quyền quản trị để ghi. Trên Linux/macOS, thư mục hệ thống cũng thường không cho tài khoản thông thường ghi.

## 5. Dùng APPDIR, BINDIR và ROOTDIR để tham chiếu resource đã đóng gói

Launcher do `jpackage` tạo hỗ trợ các token runtime:

- `$APPDIR`: thư mục chứa application payload.
- `$BINDIR`: thư mục chứa launcher executable.
- `$ROOTDIR`: thư mục gốc của application image.

Các token có thể được dùng trong `--arguments` và `--java-options`. Launcher mở rộng token khi ứng dụng chạy. Chúng giúp tham chiếu resource đã đóng gói mà không hard-code đường dẫn cài đặt của từng hệ điều hành.

Ví dụ đóng gói resource mặc định trong thư mục input:

~~~text
input/
  app.jar
  defaults/
    app.properties
  templates/
    report-template.json
~~~

Tạo application image:

~~~powershell
jpackage --type app-image --name SampleApp --input input --main-jar app.jar --main-class com.example.app.Main --java-options '-Dapp.resources=$APPDIR' --dest dist
~~~

Trong Java, đọc resource mặc định qua system property:

~~~java
import java.nio.file.Path;

Path resourceDirectory =
        Path.of(System.getProperty("app.resources"));
Path defaultConfig =
        resourceDirectory.resolve("defaults").resolve("app.properties");
~~~

`$APPDIR` ở đây chỉ tới resource được đóng gói cùng application payload. Dùng đường dẫn này để đọc file mặc định hoặc template; không dùng nó để ghi cấu hình người dùng. Tài liệu launcher cho phép macro được mở rộng trong `--java-options` và `--arguments`; tên macro phân biệt hoa thường trên Unix và không phân biệt hoa thường trên Windows.

Với resource nằm bên trong JAR, ưu tiên đọc bằng `Class.getResourceAsStream` hoặc `ClassLoader.getResourceAsStream`. Không cần chuyển resource classpath thành file chỉ để đọc nội dung.

## 6. Chọn vị trí cấu hình theo từng hệ điều hành

Java SE không cung cấp một API chuẩn duy nhất trả về thư mục cấu hình ứng dụng theo quy ước của mọi hệ điều hành. Ứng dụng desktop thường cần áp dụng quy ước nền tảng:

| Hệ điều hành | Vị trí cấu hình người dùng thường dùng | Biến môi trường liên quan |
| --- | --- | --- |
| Windows | `%APPDATA%\<App>` cho cấu hình roaming; `%LOCALAPPDATA%\<App>` cho dữ liệu cục bộ/cache | `APPDATA`, `LOCALAPPDATA` |
| Linux | `$XDG_CONFIG_HOME/<app>`; mặc định `~/.config/<app>` | `XDG_CONFIG_HOME` |
| macOS | `~/Library/Application Support/<App>` | Thường dựa trên `user.home` |

Với Linux, dữ liệu trạng thái và cache thường tách riêng theo XDG:

- `XDG_STATE_HOME`, mặc định `~/.local/state`: log hoặc trạng thái có ý nghĩa lâu dài.
- `XDG_DATA_HOME`, mặc định `~/.local/share`: dữ liệu do ứng dụng tạo.
- `XDG_CACHE_HOME`, mặc định `~/.cache`: dữ liệu có thể tái tạo.

Với macOS, cache thường đặt dưới `~/Library/Caches/<App>`. Trên Windows, dữ liệu cục bộ và cache thường phù hợp với `LOCALAPPDATA`. Chọn vị trí theo loại dữ liệu và chính sách sản phẩm; không dùng chung một file cho cấu hình, cache và dữ liệu nghiệp vụ.

## 7. Tạo config directory và xác nhận có thể ghi

Ví dụ resolver đơn giản cho thư mục cấu hình người dùng:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class AppDirectories {
    private static final String APP_ID = "ExampleCompany/SampleApp";

    private AppDirectories() {
    }

    public static Path configDirectory() throws IOException {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        Path base;

        if (os.startsWith("windows")) {
            String appData = System.getenv("APPDATA");
            base = appData == null || appData.isBlank()
                    ? Path.of(System.getProperty("user.home"),
                            "AppData", "Roaming")
                    : Path.of(appData);
        } else if (os.startsWith("mac")) {
            base = Path.of(System.getProperty("user.home"),
                    "Library", "Application Support");
        } else {
            String xdg = System.getenv("XDG_CONFIG_HOME");
            Path candidate = xdg == null || xdg.isBlank()
                    ? null : Path.of(xdg);

            base = candidate != null && candidate.isAbsolute()
                    ? candidate
                    : Path.of(System.getProperty("user.home"), ".config");
        }

        Path directory = base.resolve(APP_ID).normalize();
        Files.createDirectories(directory);

        if (!Files.isDirectory(directory) || !Files.isWritable(directory)) {
            throw new IOException(
                    "Config directory is not writable: " + directory);
        }
        return directory;
    }
}
~~~

`APP_ID` là định danh cố định do ứng dụng chọn; trong sản phẩm thực tế, có thể dùng một tên thư mục đơn giản không chứa dấu phân cách nếu muốn có cùng cấu trúc trên mọi nền tảng. Ví dụ trên minh họa quy ước đường dẫn; cần điều chỉnh tên thư mục, chính sách roaming và quyền truy cập theo sản phẩm.

`Files.createDirectories` tạo các thư mục cha còn thiếu. `Files.isWritable` là bước kiểm tra hữu ích nhưng không bảo đảm thao tác ghi tiếp theo chắc chắn thành công: ACL, quota, mount hoặc quyền có thể thay đổi giữa lúc kiểm tra và lúc ghi. Luôn xử lý `IOException` từ thao tác ghi thực tế.

Không fallback sang thư mục cài đặt nếu user config directory không ghi được. Hãy báo lỗi rõ ràng hoặc dùng fallback có chủ đích như thư mục tạm chỉ cho dữ liệu có thể tái tạo.

## 8. Phân biệt config, state, data, cache và log

Các loại file có vòng đời và mức độ quan trọng khác nhau:

| Loại dữ liệu | Ví dụ | Đặc tính | Vị trí phù hợp |
| --- | --- | --- | --- |
| Config | Endpoint, lựa chọn người dùng, tùy chọn giao diện | Nhỏ, cần tồn tại qua lần chạy | User config directory hoặc Preferences API |
| State | Trạng thái đồng bộ, checkpoint, lịch sử tác vụ | Có ý nghĩa giữa các lần chạy | User state/data directory |
| Data | Cơ sở dữ liệu local, tài liệu người dùng tạo | Có giá trị, cần backup/migrate | User data directory hoặc vị trí người dùng chọn |
| Cache | Ảnh thumbnail, kết quả tính toán có thể tạo lại | Có thể xóa và tạo lại | Cache directory của người dùng |
| Log | Log ứng dụng, diagnostic report | Có thể tăng liên tục, cần rotation | Log/state directory hoặc logging service |

Không đặt dữ liệu nghiệp vụ quan trọng trong cache. Không xóa config hoặc data khi cập nhật phiên bản nếu không có chính sách migration rõ ràng. Log không nên chứa mật khẩu, access token hoặc dữ liệu nhạy cảm không cần thiết.

## 9. Dùng Preferences API cho thiết lập nhỏ

Nếu chỉ cần lưu lựa chọn người dùng như theme, ngôn ngữ, kích thước cửa sổ hoặc tùy chọn hiển thị, có thể dùng `java.util.prefs.Preferences` thay vì tự quản lý file:

~~~java
import java.util.prefs.Preferences;

public class UserSettings {
    private static final Preferences PREFS =
            Preferences.userNodeForPackage(UserSettings.class);

    public static void saveTheme(String theme) {
        PREFS.put("theme", theme);
    }

    public static String loadTheme() {
        return PREFS.get("theme", "system");
    }
}
~~~

Preferences lưu dữ liệu vào backing store do implementation của nền tảng quyết định; ứng dụng không cần tự suy ra file hoặc registry path. Thay đổi có thể được ghi bất đồng bộ. Nếu một thao tác cần xác nhận lưu bền vững trước khi báo thành công, có thể gọi `flush()` và xử lý `BackingStoreException`.

Với ứng dụng modular, module descriptor cần:

~~~java
module com.example.app {
    requires java.prefs;
}
~~~

Preferences phù hợp với các cặp key/value nhỏ. Không dùng nó thay thế database hoặc kho file cho dữ liệu lớn, và không lưu secret nhạy cảm như mật khẩu/token nếu không có cơ chế bảo vệ phù hợp.

## 10. Đọc cấu hình mặc định và ghi override của người dùng

Một cách triển khai dễ cập nhật là giữ cấu hình mặc định ở resource bất biến và cấu hình override trong user config directory:

1. Đóng gói `defaults/app.properties` cùng ứng dụng.
2. Khi khởi động, đọc giá trị mặc định từ classpath hoặc `APPDIR`.
3. Nếu user config directory có file `app.properties`, đọc và ghi đè các khóa được phép.
4. Khi người dùng thay đổi thiết lập, chỉ ghi file override của họ.
5. Khi nâng cấp ứng dụng, resource mặc định được cập nhật theo phiên bản mới; file override của người dùng được giữ lại và migrate nếu schema thay đổi.

Ví dụ kiểm tra file override:

~~~java
Path configFile =
        AppDirectories.configDirectory().resolve("app.properties");

if (Files.exists(configFile)) {
    // Đọc cấu hình override của người dùng.
} else {
    // Dùng cấu hình mặc định đã đóng gói trong ứng dụng.
}
~~~

Không sửa trực tiếp file mặc định trong application image. Installer/update có thể thay file đó và người dùng có thể không có quyền ghi.

## 11. Ghi file cấu hình an toàn và tránh file dở dang

Khi cập nhật config, tránh ghi đè trực tiếp file đang dùng nếu ứng dụng có thể bị dừng giữa chừng. Có thể ghi file tạm trong cùng thư mục rồi đổi tên:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.StandardCopyOption;

public final class ConfigWriter {
    private ConfigWriter() {
    }

    public static void write(Path configFile, String content)
            throws IOException {
        Path directory = configFile.toAbsolutePath().getParent();
        Files.createDirectories(directory);

        Path temporary = Files.createTempFile(
                directory, "app-", ".tmp");
        try {
            Files.writeString(
                    temporary, content, StandardCharsets.UTF_8);

            try {
                Files.move(
                        temporary,
                        configFile,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ex) {
                Files.move(
                        temporary,
                        configFile,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
~~~

Atomic move chỉ được bảo đảm khi filesystem/provider hỗ trợ. Khi dùng `ATOMIC_MOVE`, các tùy chọn move khác có thể bị bỏ qua và hành vi nếu file đích đã tồn tại phụ thuộc implementation; hãy kiểm thử trên filesystem mục tiêu hoặc dùng chiến lược versioned file nếu cần bảo đảm thay thế nhất quán. Fallback vẫn cần xử lý lỗi ghi. Với dữ liệu có nhiều writer hoặc nhiều tiến trình, cần thêm chiến lược khóa, versioning hoặc transaction phù hợp. Khi lưu secret, cần thiết kế quyền file/ACL và mã hóa theo threat model; ghi vào thư mục người dùng không tự động làm dữ liệu bí mật an toàn.

## 12. Chẩn đoán quyền ghi sau cài đặt

Khi ứng dụng không tạo được file, ghi lại các thông tin không nhạy cảm:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class StorageDiagnostics {
    public static void main(String[] args) throws Exception {
        Path working = Path.of("").toAbsolutePath().normalize();
        Path home = Path.of(System.getProperty("user.home"));
        Path config = AppDirectories.configDirectory();

        System.out.println("user.dir: " + working);
        System.out.println("user.home: " + home);
        System.out.println("config: " + config);
        System.out.println("working writable: " + Files.isWritable(working));
        System.out.println("home writable: " + Files.isWritable(home));
        System.out.println("config writable: " + Files.isWritable(config));
    }
}
~~~

Không ghi ra log nội dung cấu hình, token hoặc đường dẫn chứa thông tin riêng tư nếu không cần. Trong môi trường production, nên có diagnostic mode để người dùng hoặc đội hỗ trợ lấy thông tin cần thiết mà không làm lộ dữ liệu.

Nếu ghi file thất bại:

- Xác nhận đường dẫn tuyệt đối mà ứng dụng thực sự sử dụng.
- Kiểm tra directory có tồn tại và có phải directory không.
- Kiểm tra quyền người dùng chạy ứng dụng, ACL, quota và filesystem read-only.
- Xác nhận launcher/service chạy dưới tài khoản nào.
- Kiểm tra file đã bị process khác khóa hay chưa.
- Không khắc phục bằng cách chạy toàn bộ ứng dụng với quyền administrator/root nếu chỉ cần sửa vị trí lưu file.

## 13. Kiểm thử application image và installer trên máy sạch

Nên kiểm tra theo hai giai đoạn:

**Giai đoạn A — application image**

1. Tạo app image bằng `jpackage --type app-image`.
2. Chạy launcher từ terminal với working directory khác thư mục image.
3. Chạy launcher bằng shortcut hoặc cách khởi chạy thực tế.
4. Kiểm tra resource mặc định đọc được từ `APPDIR`.
5. Kiểm tra config directory được tạo ở vùng người dùng và file override được lưu.

Ví dụ PowerShell chạy từ thư mục khác:

~~~powershell
Set-Location $env:TEMP
& "C:\build\dist\SampleApp\SampleApp.exe"
~~~

**Giai đoạn B — installer đã cài**

1. Cài ứng dụng bằng tài khoản người dùng thông thường.
2. Khởi chạy từ shortcut/menu, không chạy từ thư mục build.
3. Xác nhận ứng dụng không ghi vào thư mục cài đặt.
4. Thay đổi thiết lập, thoát và mở lại để kiểm tra persistence.
5. Cập nhật ứng dụng và xác nhận config/data người dùng còn nguyên.
6. Gỡ cài đặt theo chính sách sản phẩm và xác nhận dữ liệu người dùng được giữ hoặc xóa đúng lựa chọn đã công bố.

Lặp lại trên Windows, Linux và macOS nếu sản phẩm hỗ trợ các nền tảng đó. Test bằng tài khoản không có quyền quản trị để phát hiện lỗi quyền ghi bị che khuất trên máy phát triển.

## 14. Checklist trước khi phát hành

- Không dùng `user.dir` làm thư mục cài đặt hoặc vị trí lưu config lâu dài.
- Không ghi config/data/log/cache vào application image hoặc thư mục cài đặt.
- Dùng `APPDIR`/`BINDIR`/`ROOTDIR` chỉ để tham chiếu resource hoặc vị trí launcher phù hợp.
- Tách config, state, data, cache và log theo vòng đời.
- Chọn thư mục người dùng theo quy ước Windows, XDG Linux và macOS.
- Tạo directory bằng `Files.createDirectories` và xử lý lỗi ghi thực tế.
- Dùng Preferences API cho thiết lập nhỏ nếu phù hợp.
- Giữ file mặc định bất biến; ghi override của người dùng ở user config directory.
- Dùng cập nhật file an toàn và có chiến lược xử lý nhiều writer.
- Test launcher từ working directory khác và test installer bằng tài khoản thường.
- Kiểm tra cập nhật/gỡ cài đặt không làm mất dữ liệu người dùng ngoài chính sách đã công bố.

**Ghi nhớ:** `user.dir` là working directory của tiến trình, không phải thư mục cài đặt. Application image do `jpackage` tạo chứa launcher, app payload và runtime; vị trí cài đặt thường không phù hợp để ghi dữ liệu người dùng. Dùng `APPDIR` để đọc resource đã đóng gói, còn config/data cần nằm trong thư mục người dùng theo quy ước nền tảng hoặc Preferences API. Luôn kiểm thử bằng launcher và installer trên tài khoản không có quyền quản trị.

## Nguồn tham khảo chính thức

- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Packaging Tool User's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/index.html)
- [System API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html)
- [Path API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html)
- [Files API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
- [Preferences API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.prefs/java/util/prefs/Preferences.html)
