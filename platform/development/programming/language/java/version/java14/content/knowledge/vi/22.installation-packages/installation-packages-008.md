# Kiểm thử cài mới, nâng cấp, gỡ và giữ dữ liệu người dùng với gói cài đặt Java

## 1. Mục tiêu của bài học

Một bản ứng dụng Java được tạo thành công bằng `jpackage` **chưa có nghĩa là có thể phát hành an toàn**. Gói cài đặt (native installer) phải được kiểm thử ít nhất bốn đường đi quan trọng:

1. **Cài mới (fresh install):** cài trên hệ điều hành hoặc hồ sơ người dùng chưa từng có ứng dụng.
2. **Nâng cấp (upgrade):** cài bản mới lên hệ thống đang có bản cũ và dữ liệu thực tế.
3. **Gỡ cài đặt (uninstall):** loại bỏ thành phần do gói cài đặt quản lý, không làm hỏng máy hoặc ứng dụng khác.
4. **Giữ dữ liệu người dùng (user-data retention):** xác minh cấu hình, tài liệu, sở thích và dữ liệu riêng được giữ, di chuyển hay xóa **đúng chính sách đã công bố**.

Điểm khó nhất không phải chỉ là launcher chạy được, mà là **phân biệt rõ dữ liệu thuộc gói ứng dụng với dữ liệu thuộc người dùng**.

- **Dữ liệu ứng dụng được cài:** executable, Java runtime đóng kèm, JAR/module, thư viện, icon, shortcut, file mẫu do installer quản lý. Những thành phần này thường bị thay thế khi nâng cấp và bị gỡ khi uninstall.
- **Dữ liệu người dùng:** cấu hình được người dùng sửa, cơ sở dữ liệu cá nhân, tài liệu và state sau lần chạy đầu. Nó cần được lưu ở vị trí thích hợp, có chính sách backup/migration và không phụ thuộc vào thư mục cài đặt.
- **Dữ liệu cache/tạm:** có thể xóa/tái tạo theo chính sách, nhưng không nên mặc nhiên coi toàn bộ thư mục của ứng dụng là cache.

**Ngữ cảnh Java 14 và tính hiện hành:** `jpackage` được giới thiệu như công cụ ươm tạo ở Java 14 và **trở thành công cụ JDK chính thức từ Java 16**. Bài này sử dụng cú pháp và API **Java 17+**, tập trung vào quy trình kiểm thử vẫn còn cần thiết; không hướng dẫn kích hoạt incubator hay dùng tùy chọn legacy.

**Nguyên tắc:** Không có bảo đảm phổ quát rằng tất cả installer do `jpackage` tạo sẽ luôn giữ hoặc luôn xóa dữ liệu riêng của người dùng. Kết quả phụ thuộc **nơi ứng dụng ghi dữ liệu**, backend installer của hệ điều hành và các script/custom action được cấu hình. **Phải kiểm chứng trên bản cài thật**, không chỉ dựa vào suy đoán.

## 2. Phân biệt application image và native installer

`jpackage` hỗ trợ hai nhóm kết quả:

| Kết quả | Tùy chọn | Điều có thể kiểm tra |
| --- | --- | --- |
| Application image | `--type app-image` | Launcher, Java runtime đi kèm, phụ thuộc, tài nguyên, khả năng chạy |
| Native installer Windows | `--type msi` hoặc `--type exe` | Cài/gỡ qua Windows, quyền admin hoặc per-user, Start Menu, nâng cấp |
| Native package Linux | `--type deb` hoặc `--type rpm` | Cài/gỡ bằng package manager, phiên bản và dependency hệ thống |
| Gói phân phối macOS | `--type pkg` hoặc `--type dmg` | Bundle được cài/sao chép, nhận diện ứng dụng, hành vi cập nhật/gỡ phù hợp kiểu gói |

**`app-image` không kiểm chứng được toàn bộ installer:** chạy launcher trong image mới chỉ cho thấy ứng dụng hoạt động. Nó **không chứng minh** các bước setup/uninstall, registry/shortcut/receipt, quyền cài đặt hay upgrade của native package sẽ đúng.

`jpackage` **không hỗ trợ cross-platform packaging**. Để kiểm thử Windows, Linux, macOS, tạo installer bằng runner/máy cùng OS rồi thực hiện kiểm thử ở môi trường tương ứng. Các dạng installer khác nhau không có một lệnh uninstall chung.

### Những tùy chọn có ảnh hưởng đến kiểm thử nâng cấp

| Tham số | Vai trò |
| --- | --- |
| `--name` | Nhận diện ứng dụng/gói và tên launcher; nên ổn định qua các bản |
| `--app-version` | Phiên bản ứng dụng/gói; cần **tăng đúng** và tuân theo quy tắc OS |
| `--install-dir` | Vị trí cài đặt, **không phải** vị trí nên ghi dữ liệu user |
| `--win-per-user-install` | Windows: cài theo người dùng, khác với cài phạm vi máy |
| `--win-upgrade-uuid` | Windows: UUID liên kết các gói có thể nâng cấp nhau |
| `--linux-package-name` | Linux: tên gói do package manager nhận diện |
| `--linux-app-release` | Linux: release/revision trong metadata package |
| `--mac-package-identifier` | macOS: nhận diện gói ứng dụng; cần nhất quán theo chiến lược phát hành |
| `--win-menu`, `--win-shortcut` | Windows: lối tắt cần kiểm tra sau cài/gỡ |

Không tự thay tên package, UUID nâng cấp hoặc phạm vi cài đặt giữa các phiên bản nếu không có một **kế hoạch di chuyển**. Đặc biệt, cùng tên launcher chưa chắc đã đủ để Windows Installer coi hai gói là một chuỗi nâng cấp.

## 3. Lưu dữ liệu người dùng ở đâu cho đúng?

**Không lưu dữ liệu phải tồn tại qua nâng cấp vào thư mục app image hoặc thư mục cài đặt.** Những vị trí như `Program Files` trên Windows hoặc thư mục bundle ứng dụng có thể yêu cầu quyền cao, bị thay thế khi cập nhật và bị gỡ trong quá trình uninstall.

Thay vào đó, dùng thư mục dữ liệu **phù hợp với tài khoản và hệ điều hành**:

| Hệ điều hành | Vị trí thường thích hợp cho dữ liệu ứng dụng theo người dùng | Lưu ý |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\LessonDesk`, hoặc `%APPDATA%\LessonDesk` nếu cần dữ liệu roaming đúng nghĩa | Không nên mặc định ghi vào `C:\Program Files\LessonDesk` |
| Linux | `$XDG_DATA_HOME/lessondesk`, nếu biến không được đặt thì `~/.local/share/lessondesk` | Phân biệt `XDG_DATA_HOME` với `XDG_CONFIG_HOME` khi thiết kế config |
| macOS, app desktop không sandboxed | `~/Library/Application Support/LessonDesk` | App sandboxed có đường dẫn container riêng; không hardcode cách suy luận cho mọi app |

Đây là những **vị trí quy ước**, không phải hợp đồng rằng mọi backend `jpackage` tự động tạo và quản lý chúng. **Ứng dụng Java phải tự chọn và sử dụng** vị trí dữ liệu thích hợp. Trên Windows, nếu ứng dụng cần truy vấn Known Folder chính xác trong nhiều trường hợp redirection/chính sách doanh nghiệp, có thể dùng API nền tảng/thư viện chuyên dụng thay vì chỉ đoán bằng đường dẫn cố định.

### Vì sao cần tách dữ liệu khỏi vị trí cài đặt?

Giả sử bản 1.0.0 ghi `prefs.properties` vào:

```text
C:\Program Files\LessonDesk\prefs.properties
```

Các rủi ro gồm: người dùng thường không có quyền ghi, chương trình bị lỗi khi cài vào thư mục bảo vệ, installer nâng cấp thay thế/xóa dữ liệu, hoặc gỡ cài đặt xóa luôn file tùy chỉnh.

Với thiết kế phù hợp hơn:

```text
C:\Program Files\LessonDesk\...       <- mã và runtime do installer quản lý
%LOCALAPPDATA%\LessonDesk\prefs.properties  <- sở thích người dùng
```

Việc cập nhật file ứng dụng và cập nhật user data lúc này có **ranh giới khác nhau**. Tuy vậy, installer tùy biến hoặc công cụ dọn dẹp vẫn có thể xóa dữ liệu hồ sơ. Do đó, **giữ dữ liệu phải được thử nghiệm**, không chỉ chứng minh hai đường dẫn khác nhau.

### Một chính sách dữ liệu nên ghi rõ

- Những dữ liệu nào là **tài liệu người dùng cần giữ**?
- Dữ liệu nào cần **migrate** giữa schema cũ và mới?
- Cache nào có thể xóa và được tạo lại?
- Gỡ ứng dụng có **giữ mặc định** dữ liệu người dùng, hay đưa ra lựa chọn xóa có xác nhận?
- Nếu người dùng cài lại sau nhiều tháng, bản mới có đọc được dữ liệu cũ không?
- Dữ liệu cần backup/export ở đâu, với quyền truy cập và thời hạn lưu thế nào?
- Điều gì xảy ra khi dữ liệu cũ không tương thích với bản mới hoặc khi migration thất bại?

**Không tự động xóa dữ liệu người dùng trong script gỡ nếu không có chính sách rõ ràng và sự đồng ý tương ứng.** Với dữ liệu quan trọng, cần backup và khả năng phục hồi thay vì coi file riêng tư như tài nguyên của installer.

## 4. Ma trận kiểm thử cài mới, nâng cấp, gỡ và cài lại

Mỗi hàng kiểm thử cần ghi **môi trường, phiên bản trước/sau, trạng thái dữ liệu trước/sau và bằng chứng**. Một ma trận mẫu:

| ID | Tình huống | Các bước chủ yếu | Tiêu chí PASS |
| --- | --- | --- | --- |
| F01 | Máy/user sạch, cài 1.0.0 | Cài bản 1, kiểm tra launcher và chạy lần đầu | Ứng dụng mở được, phiên bản đúng, tạo dữ liệu đầu tiên |
| F02 | Cài trên user thường | Chạy installer theo đúng phạm vi `per-user`/`per-machine` | Quyền truy cập và đường dẫn đúng, không yêu cầu admin ngoài thiết kế |
| F03 | Lần chạy đầu rồi khởi động lại app | Đổi sở thích, đóng và mở lại | Giá trị đã chỉnh sửa còn nguyên |
| U01 | Nâng cấp 1.0.0 → 2.0.0 | Đóng app, cài bản 2, chạy lại | Launcher/version là bản mới; dữ liệu của user vẫn đọc được |
| U02 | Migration schema 1 → 2 | Chuẩn bị dữ liệu thực của bản 1, nâng cấp, kiểm tra migration | Schema mới hợp lệ, giá trị nghiệp vụ không mất, có backup nếu quy định |
| U03 | Cài lại cùng phiên bản | Chạy lại bộ cài theo kịch bản được hỗ trợ | Không vô tình reset dữ liệu hoặc tạo cài đặt trùng |
| U04 | Nâng cấp khi app còn chạy | Mở app rồi thử cập nhật trong môi trường kiểm thử | Installer xử lý file lock/nhắc đóng/reboot theo thiết kế, không hỏng dữ liệu |
| U05 | Nâng cấp với dữ liệu thiếu/hỏng | Thử file lỗi, disk full hoặc quyền không đủ trên VM | Thất bại có thông báo, không làm mất dữ liệu gốc; có cách phục hồi |
| R01 | Gỡ bản đã cài | Đóng app, uninstall đúng cách của OS | Thành phần gói, launcher, shortcut/registry/receipt được dọn đúng |
| R02 | Xác minh dữ liệu sau uninstall | Kiểm tra thư mục user data và các hash/giá trị | Dữ liệu được giữ hay xóa **đúng chính sách đã định** |
| R03 | Cài lại sau khi gỡ | Cài bản tương thích, chạy lại | Dữ liệu giữ được có thể đọc lại hoặc hành vi first-run đúng |
| M01 | Hai tài khoản trên cùng máy | Dùng app dưới user A/B, cài theo scope xác định | Dữ liệu user A không bị user B vô tình ghi đè |
| M02 | Installer khác OS/kiến trúc | Test trên matrix Windows/Linux/macOS mục tiêu | Package native hoạt động đúng trên từng OS/kiến trúc được hỗ trợ |

**Quan trọng:** Các ca R01/R02 **không mặc định phải xóa mọi file có tên ứng dụng**. Nếu chính sách “Uninstall giữ dữ liệu để dễ cài lại”, việc `prefs.properties` còn tồn tại là **PASS**, không phải lỗi. Nếu người dùng **chủ động yêu cầu xóa dữ liệu riêng**, kiểm thử đường đi xóa dữ liệu cần được thiết kế riêng, có xác nhận và kiểm tra phạm vi.

## 5. Bài thực hành Java 17+: dữ liệu còn tồn tại giữa hai bản app image

Trước khi thử native installer, có thể kiểm chứng **cơ chế dữ liệu độc lập với thư mục ứng dụng** bằng ứng dụng Java nhỏ. Bài thực hành này dùng hai app image **1.0.0** và **2.0.0**, ghi dữ liệu ở **thư mục giả lập user data tách biệt**, migration schema và sao lưu.

**Phạm vi kiểm chứng:** Đây là thử nghiệm **app-image/data lifecycle** trên môi trường tạm, **không phải bằng chứng đã chạy trình cài đặt/gỡ native**. Các bước cài mới, nâng cấp và uninstall của `msi`/`exe`/`deb`/`rpm`/`pkg`/`dmg` vẫn phải kiểm tra theo ma trận phần 4.

### 5.1. Mã nguồn `src/InstallDataDemo.java`

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Locale;
import java.util.Properties;

public final class InstallDataDemo {
    private static Path dataDirectory() {
        String override = System.getenv("LESSON_DATA_DIR");
        if (override != null && !override.isBlank()) {
            return Path.of(override).toAbsolutePath();
        }

        String home = System.getProperty("user.home");
        String os = System.getProperty("os.name").toLowerCase(Locale.ROOT);
        if (os.contains("win")) {
            String local = System.getenv("LOCALAPPDATA");
            Path base = local != null && !local.isBlank()
                    ? Path.of(local) : Path.of(home, "AppData", "Local");
            return base.resolve("LessonDesk");
        }
        if (os.contains("mac")) {
            return Path.of(home, "Library", "Application Support", "LessonDesk");
        }

        String xdg = System.getenv("XDG_DATA_HOME");
        Path base = xdg != null && !xdg.isBlank() && Path.of(xdg).isAbsolute()
                ? Path.of(xdg) : Path.of(home, ".local", "share");
        return base.resolve("lessondesk");
    }

    private static Properties load(Path file) throws IOException {
        Properties result = new Properties();
        if (Files.exists(file)) {
            try (InputStream input = Files.newInputStream(file)) {
                result.load(input);
            }
        }
        return result;
    }

    private static void store(Path file, Properties value) throws IOException {
        Files.createDirectories(file.getParent());
        Path temp = Files.createTempFile(file.getParent(), "prefs-", ".tmp");
        try {
            try (OutputStream output = Files.newOutputStream(temp)) {
                value.store(output, "LessonDesk preferences");
            }
            Files.move(temp, file, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Use: InstallDataDemo <release> <init|migrate|read>");
        }

        String release = args[0];
        String action = args[1];
        Path file = dataDirectory().resolve("prefs.properties");
        Path backup = dataDirectory().resolve("prefs.properties.bak");

        switch (action) {
            case "init" -> {
                if (!Files.exists(file)) {
                    Properties initial = new Properties();
                    initial.setProperty("schema", "1");
                    initial.setProperty("theme", "dark");
                    store(file, initial);
                }
            }
            case "migrate" -> {
                if (!Files.exists(file)) {
                    throw new IllegalStateException("No user data to migrate");
                }
                Properties existing = load(file);
                if ("1".equals(existing.getProperty("schema"))) {
                    Files.copy(file, backup,
                            StandardCopyOption.REPLACE_EXISTING);
                    existing.setProperty("schema", "2");
                    store(file, existing);
                }
            }
            case "read" -> { }
            default -> throw new IllegalArgumentException(
                    "Unknown action: " + action);
        }

        Properties saved = load(file);
        System.out.println("release=" + release);
        System.out.println("schema=" +
                saved.getProperty("schema", "<missing>"));
        System.out.println("theme=" +
                saved.getProperty("theme", "<missing>"));
        System.out.println("backupPresent=" + Files.exists(backup));
    }
}
```

**Giải thích cấu trúc:**

- `dataDirectory()` chọn vị trí user data theo môi trường. Biến `LESSON_DATA_DIR` cho phép **ghi đè thư mục chỉ trong bài kiểm thử**, để không làm bẩn hồ sơ thật. Đây là biến riêng do ứng dụng demo định nghĩa, **không phải biến JDK hay tùy chọn `jpackage` tiêu chuẩn**.
- Với Windows dùng `LOCALAPPDATA`; macOS desktop không sandboxed dùng `Library/Application Support`; Linux tôn trọng `XDG_DATA_HOME` nếu đó là đường dẫn tuyệt đối và fallback sang `.local/share`.
- `init` khởi tạo file cấu hình `schema=1`, `theme=dark` **chỉ khi file chưa tồn tại**, tránh reset sở thích khi mở lại.
- `migrate` yêu cầu dữ liệu cũ, sao lưu thành `prefs.properties.bak`, rồi nâng schema lên `2` nhưng giữ `theme`.
- `read` đọc lại mà không thay đổi file.
- `load`/`store` dùng `Properties` để thao tác dữ liệu có cấu trúc; `try-with-resources` đóng stream I/O và temp file được xóa trong `finally`.

**Giới hạn mẫu:** Đây là demo một tiến trình, không phải thư viện lưu trữ production-grade. `Files.move(..., REPLACE_EXISTING)` trong ví dụ **không bảo đảm atomic/durable trên mọi filesystem**. Trong ứng dụng quan trọng cần thêm xử lý `ATOMIC_MOVE` khi được hỗ trợ, backup/restore rõ ràng, kiểm soát truy cập, khóa chống ghi đồng thời, chống ghi vào symlink ngoài dự kiến và chiến lược rollback khi migration thất bại.

Ngoài ra, dữ liệu nhạy cảm không nên được lưu thuần văn bản trong `Properties` nếu chính sách bảo mật yêu cầu mã hóa hoặc hệ quản lý bí mật phù hợp.

### 5.2. Chuẩn bị và build trên Windows PowerShell

Các bước sau **không cài hay gỡ bất kỳ phần mềm nào trên máy**. Chúng tạo file build trong thư mục dự án và dùng môi trường test tách riêng.

Sau khi đặt mã nguồn vào `src/InstallDataDemo.java`, ở thư mục project:

```powershell
New-Item -ItemType Directory -Force classes,input,v1,v2,test-user-data | Out-Null

javac --release 17 -d classes src\InstallDataDemo.java
jar --create --file input\lesson-data.jar -C classes .
```

Tạo **hai app image** của cùng demo với metadata version riêng:

```powershell
jpackage --type app-image --name LessonDesk --app-version 1.0.0 --input input --main-jar lesson-data.jar --main-class InstallDataDemo --dest v1 --win-console
jpackage --type app-image --name LessonDesk --app-version 2.0.0 --input input --main-jar lesson-data.jar --main-class InstallDataDemo --dest v2 --win-console
```

Hai bản image ở **hai thư mục đầu ra riêng**:

```text
v1/LessonDesk/LessonDesk.exe
v2/LessonDesk/LessonDesk.exe
test-user-data/
```

**Lưu ý:** Demo truyền `release` như tham số CLI nhằm chứng minh bài thử. `--app-version` là **metadata đóng gói**, không tự xuất hiện thành `args[0]` của `main`. Trong bản phát hành thật, dùng nguồn version của hệ thống build hoặc metadata application phù hợp, không suy luận từ giá trị demo.

### 5.3. Chạy kiểm thử giữ dữ liệu qua hai image

Dùng PowerShell đặt biến môi trường test chỉ cho phiên shell đang chạy:

```powershell
$env:LESSON_DATA_DIR = (Resolve-Path .\test-user-data).Path

.\v1\LessonDesk\LessonDesk.exe 1.0.0 init
.\v1\LessonDesk\LessonDesk.exe 1.0.0 init
.\v2\LessonDesk\LessonDesk.exe 2.0.0 migrate
.\v2\LessonDesk\LessonDesk.exe 2.0.0 read
```

**Stdout đã kiểm chứng trên Windows bằng `javac --release 17` và `jpackage` chính thức:**

```text
release=1.0.0
schema=1
theme=dark
backupPresent=false
release=1.0.0
schema=1
theme=dark
backupPresent=false
release=2.0.0
schema=2
theme=dark
backupPresent=true
release=2.0.0
schema=2
theme=dark
backupPresent=true
```

Điều được kiểm chứng:

1. Lần chạy đầu **tạo** user data với `schema=1` và `theme=dark`.
2. Gọi `init` lần hai **không ghi đè** giá trị đã có.
3. Bản app image 2.0.0 đọc **cùng thư mục dữ liệu độc lập**, sao lưu file cũ và migrate schema từ 1 sang 2.
4. Sau migration, `theme=dark` **được giữ nguyên**, schema đổi thành `2`, và file backup tồn tại.
5. Lệnh `read` không làm mất dữ liệu hay reset state.

Nếu cần kiểm tra file ở PowerShell:

```powershell
Get-Content .\test-user-data\prefs.properties
Test-Path .\test-user-data\prefs.properties.bak
Get-FileHash -Algorithm SHA256 .\test-user-data\prefs.properties
```

Nội dung `Properties.store` có comment và timestamp sinh lúc ghi, nên **không lấy một hash cố định của file demo** làm expected output. Với migration làm thay đổi schema, hash file cũ và file mới **nên khác nhau**; so sánh các giá trị logic như `theme`, `schema` và kiểm tra backup mới là kiểm thử phù hợp.

### 5.4. Thử “gỡ app image” trong sandbox tạm

Vì đây là app image chứ **không phải native installer**, có thể đóng launcher và **di chuyển/xóa bản image v1 chỉ trong thư mục thử nghiệm** rồi chạy lại v2. Thao tác đó mô phỏng việc mất file chương trình cũ nhưng **không kiểm tra registry, package manager hay quy trình uninstall thật**.

Trong môi trường test đã chuẩn bị, kiểm tra bằng tay rằng:

- Thư mục `test-user-data` **nằm ngoài** `v1` và `v2`.
- Xóa `v1/LessonDesk` **chỉ khi biết chắc đây là bản test**; không dùng lệnh xóa rộng ở thư mục người dùng hoặc thư mục cài đặt thật.
- Bản `v2` vẫn đọc được `schema=2`, `theme=dark` bằng lệnh `read`.
- Khi kết thúc, chỉ dọn những tệp **do bài thử tạo ra**, không xóa thư mục user data thực tế nếu trước đó bỏ biến `LESSON_DATA_DIR`.

Bài thực hành này xác nhận **thiết kế vị trí dữ liệu** và một bước migration đơn giản. Nó không thay thế ca R01/R02 của installer native ở phần 4.

## 6. Kiểm thử native installer trên Windows

Một chiến dịch kiểm thử đầy đủ nên dùng **máy ảo hoặc môi trường kiểm thử riêng**, có snapshot và tài khoản user thường. Không thử gỡ/cài đè một ứng dụng đang được người khác sử dụng trên máy làm việc.

### 6.1. Tạo bộ cài v1 và v2

Với Windows, có thể dùng `jpackage --type msi` hoặc `--type exe` khi có đủ công cụ native tương thích với phiên bản JDK. Ví dụ hai lệnh sau dành cho **môi trường build Windows**, không phải hai bước đã chạy trong bài thực hành app image:

```powershell
jpackage --type msi --name LessonDesk --app-version 1.0.0 --win-upgrade-uuid 6d31a5a4-4dd1-47cc-8d77-47a30f36f4b2 --win-per-user-install --input input --main-jar lesson-data.jar --main-class InstallDataDemo --dest installers-v1 --win-console

jpackage --type msi --name LessonDesk --app-version 2.0.0 --win-upgrade-uuid 6d31a5a4-4dd1-47cc-8d77-47a30f36f4b2 --win-per-user-install --input input --main-jar lesson-data.jar --main-class InstallDataDemo --dest installers-v2 --win-console
```

**Điểm cần kiểm tra về hai lệnh:**

- `--name` giữ ổn định là `LessonDesk`.
- `--app-version` tăng từ `1.0.0` lên `2.0.0`.
- `--win-upgrade-uuid` **giống nhau** ở hai bản để liên kết quá trình nâng cấp. UUID ví dụ trên phải được **thay bằng UUID do dự án tự tạo một lần và lưu cố định**, không dùng chung giữa các ứng dụng khác nhau.
- `--win-per-user-install` giữ cùng **phạm vi cài đặt** ở hai phiên bản. Nếu chính sách sản phẩm là per-machine, hãy thiết kế và test luồng đó riêng.
- `--win-console` cho phép chạy launcher console của demo; với ứng dụng GUI thông thường có thể không cần.
- Build MSI có thể cần **tool Windows Installer/WiX tương thích** với JDK hiện tại. Kiểm tra `jpackage --help` trên máy build và hướng dẫn của phiên bản JDK cụ thể.

**Mã `InstallDataDemo` là công cụ test CLI** nhận hai tham số. Sau khi cài đặt, cần chạy launcher với các tham số `1.0.0 init`, `2.0.0 migrate` hoặc `2.0.0 read` khi kiểm tra, không chỉ bấm launcher không có tham số và kỳ vọng demo chạy như một GUI hoàn chỉnh.

### 6.2. Trình tự kiểm thử an toàn trên VM

1. **Snapshot sạch:** không có `LessonDesk` được cài; user data test đã được xác định; chọn tài khoản test.
2. **Cài MSI v1:** mở installer trong VM; quan sát prompt/installer log, lối tắt và vị trí cài. Đừng tự ghi đè file nội bộ bằng tay.
3. **Chạy v1:** xác minh launcher, tham số và dữ liệu sau `init`; chỉnh một giá trị tùy chọn để chắc chắn có state **do user tạo**, không chỉ dữ liệu mặc định.
4. **Backup dữ liệu:** ghi nhận đường dẫn, hash hoặc bản sao `prefs.properties` trước nâng cấp, đồng thời lưu metadata package v1.
5. **Nâng cấp:** đóng app, chạy MSI v2 từ đúng chuỗi nâng cấp; quan sát installer phát hiện/loại bản cũ theo thiết kế, không để trùng bản ngoài ý muốn.
6. **Chạy v2:** kiểm tra launcher/version, dữ liệu, migration và backup. Sau nâng cấp, không chỉ kiểm tra “chạy được” mà phải kiểm tra **giá trị nghiệp vụ**.
7. **Gỡ bản v2:** dùng **Windows Settings → Apps → Installed apps** hoặc cơ chế gỡ được installer đăng ký. Xác minh file ứng dụng, shortcut và entry cài đặt được dọn theo chính sách.
8. **Kiểm tra user data:** nếu chính sách giữ dữ liệu, xác nhận file và giá trị vẫn còn; nếu có lựa chọn xóa dữ liệu đã được user chấp thuận, kiểm tra chỉ đúng phạm vi được xóa.
9. **Cài lại:** cài một bản tương thích và xác nhận ứng dụng nhận lại dữ liệu đã giữ.

**Không thử lệnh uninstall hàng loạt bằng tên chung**. Nếu tự động hóa với `msiexec /x`, phải xác định **ProductCode chính xác của bản cài trong VM**, kiểm tra quyền, trạng thái tiến trình và log; không suy ProductCode từ `--win-upgrade-uuid` vì chúng là hai định danh có mục đích khác nhau.

### 6.3. Per-user, per-machine và user profile khác nhau

Windows có hai phạm vi quan trọng:

- **Per-user:** cài cho tài khoản hiện tại, đường dẫn cài mặc định có thể nằm trong `AppData\Local`. **Không vì vậy mà dùng chính thư mục cài đó làm nơi lưu preferences**; tạo thư mục dữ liệu riêng.
- **Per-machine:** cài cho nhiều người dùng, thường trong `Program Files` và có thể cần quyền cao. Dữ liệu theo từng user vẫn nên nằm trong profile của **người dùng đang chạy app**.

Bộ cài chạy elevated dưới **tài khoản khác** có thể quan sát profile khác. Cần test cài đặt và chạy ứng dụng theo đúng user/scope để tránh kết luận sai rằng dữ liệu đã mất.

Nếu chương trình tạo dữ liệu trong `%LOCALAPPDATA%\LessonDesk`, hãy xác minh **tài khoản nào** đang sở hữu thư mục ấy. Tương tự, kiểm thử nhiều user để tránh rò rỉ dữ liệu xuyên tài khoản.

## 7. Linux và macOS: cùng mục tiêu, cơ chế gỡ khác nhau

### 7.1. Linux: package manager quyết định nhiều bước

Với `deb`/`rpm`, kiểm thử tương ứng với công cụ distro, ví dụ:

- Debian/Ubuntu: cài/upgrade bằng `apt`/`dpkg` theo chính sách distro, gỡ bằng `apt remove` hoặc `dpkg -r`.
- Fedora/RHEL tương thích: cài/upgrade/gỡ bằng `dnf`/`rpm` theo quy trình tương ứng.
- Kiểm tra tên package ổn định với `--linux-package-name`, version/release phù hợp, dependency và file ownership do package manager quản lý.

**Phân biệt `remove` và `purge` trong môi trường Debian:** hai thao tác có ý nghĩa khác nhau đối với config **do package quản lý**. Không coi đó là lời hứa rằng dữ liệu cá nhân trong `$HOME` luôn bị xóa hoặc luôn được giữ. Installer có thể có script riêng và quy tắc theo distro. **Kiểm tra thực tế bằng user home test riêng**, không xóa `~/.local/share` toàn bộ.

### 7.2. macOS: `dmg` và `pkg` không giống nhau

- Với `dmg`, quy trình thường là mở disk image, kéo app vào `Applications` hoặc vị trí cho phép, chạy và gỡ app bundle theo hướng dẫn sản phẩm.
- Với `pkg`, có receipt/installer process và có thể cài vào các vị trí hệ thống. **Không có một lệnh uninstall phổ quát** cho mọi package chỉ bằng cách gọi `pkgutil`.
- `pkgutil --forget` **chỉ quên receipt**, không có nghĩa đã xóa các file đã cài. Không dùng nó như phép thử uninstall toàn bộ.
- Với app không sandboxed, dữ liệu bền vững thường ở `~/Library/Application Support/ tên ứng dụng`. Với app sandboxed, đường dẫn container có khác biệt.
- Kiểm tra identifier, version, quyền ký/notarization nếu quy trình phát hành yêu cầu.

**Điểm chung:** ứng dụng có thể cài lại/được nâng cấp bằng cơ chế OS nhưng dữ liệu nằm trong user profile. Hành vi giữ/xóa phải được kiểm tra trên sandbox/VM hoặc tài khoản thử nghiệm, không tự áp dụng hành vi của Windows sang Linux/macOS.

## 8. Kiểm thử migration và bảo vệ dữ liệu quan trọng

Không ít bản nâng cấp thay đổi **định dạng dữ liệu**, **schema database**, **kiểu dữ liệu** hoặc **mã hóa**. Ngay cả khi file vẫn nằm nguyên vị trí, bản mới có thể không đọc được nội dung cũ.

### Một lộ trình migration đúng

1. Kiểm tra **schemaVersion** hoặc định danh định dạng thật trong file/database; không chỉ dựa vào `--app-version`.
2. Có đường đi migration được thiết kế, ví dụ `schema 1 → schema 2`.
3. **Backup dữ liệu gốc** trước khi thay đổi.
4. Thực hiện migration an toàn; cân nhắc ghi file tạm và đổi tên nguyên tử khi filesystem hỗ trợ, giao dịch database và fsync khi cần.
5. Xác minh **dữ liệu logic** sau migration: trường user đã chỉnh sửa, số bản ghi, tính toàn vẹn, quan hệ khóa/giá trị.
6. Nếu migration thất bại, giữ dữ liệu gốc hoặc có quy trình restore từ backup; log lỗi có thể hành động nhưng tránh lộ bí mật.
7. Nếu rollback về bản cũ không được hỗ trợ vì schema mới, **ghi rõ** và thử khôi phục backup theo quy trình; không âm thầm mở file v2 bằng app v1 rồi làm hỏng dữ liệu.

**Ví dụ:** Trong bài thực hành, `theme=dark` phải được giữ nguyên dù `schema` đổi từ `1` sang `2`. Nếu chỉ kiểm tra “file còn tồn tại” thì chưa đủ vì nội dung có thể đã bị reset thành cấu hình mặc định.

### Cần thêm các ca lỗi

| Tình huống | Kỳ vọng tối thiểu |
| --- | --- |
| Không có file dữ liệu lần đầu | Khởi tạo hợp lệ, không ném lỗi gây crash |
| File cũ hợp lệ | Migration đúng và giữ toàn bộ dữ liệu cần thiết |
| File đã ở schema mới | Chạy migration lại không thay đổi hoặc gây hỏng dữ liệu |
| File hỏng hoặc schema không biết | Thông báo, bảo vệ backup, không tự xóa dữ liệu |
| Không đủ quyền ghi, disk full | Thất bại có xử lý, giữ file trước đó |
| Hai tiến trình cùng ghi | Có khóa/điều phối hoặc conflict handling |
| Người dùng thay đổi settings ngay trước upgrade | Giá trị mới nhất còn nguyên |
| Downgrade v2 → v1 | Không hỏng dữ liệu; từ chối hoặc rollback bằng backup nếu cần |
| Uninstall trong lúc app đang chạy | Không làm hỏng dữ liệu và xử lý file lock theo chính sách OS |
| Cài lại dưới user khác | Không đọc nhầm dữ liệu của tài khoản trước |

**Lưu ý:** Các script cài/gỡ trong dự án thực phải được audit riêng. Không có gì trong `jpackage` tự bảo đảm migration đúng với dữ liệu nghiệp vụ.

## 9. Bằng chứng QA: đo cái gì, lưu ở đâu?

Một ca kiểm thử tốt cần có bằng chứng thay vì chỉ ghi “đã cài được”.

| Bằng chứng | Cách thu thập hợp lý |
| --- | --- |
| Bản build/installer nào được test | Ghi version, SHA-256 artifact và OS/kiến trúc |
| Ứng dụng cũ đã cài | Chụp/log thông tin phiên bản, launcher, location |
| Trạng thái user data trước upgrade | Backup, file manifest và nội dung thử nghiệm đã phi định danh |
| Trạng thái sau upgrade | Đọc lại giá trị, schema, số bản ghi; so sánh theo ngữ nghĩa |
| Thành công/thất bại installer | Lấy installer/package manager logs, exit code |
| Uninstall cleanup | Kiểm tra entry installer, launcher, shortcut, thư mục do gói quản lý |
| User data retention | Kiểm tra file/giá trị ở thư mục user data, so với policy |
| Reinstall | Mở app và xác nhận nhận lại cấu hình hoặc chạy first-run đúng |

**Hash không phải thước đo duy nhất.** Nếu migration có chủ đích thay cấu trúc dữ liệu, SHA-256 có thể đổi dù thông tin người dùng vẫn giữ nguyên. Dùng hash để xác định artifact hoặc dữ liệu **đáng lẽ không đổi**; dùng semantic assertions với dữ liệu được migrate.

Tránh chụp hoặc đăng log chứa mật khẩu, token, nội dung riêng tư của khách hàng. Dùng dữ liệu thử nghiệm tổng hợp/được phép và xóa/ẩn thông tin nhạy cảm trước khi lưu báo cáo QA.

### Tiêu chí release gate ví dụ

Chỉ cho phép phát hành nếu:
- Cài mới PASS trên OS/scope mục tiêu.
- Nâng cấp từ **những phiên bản nguồn được hỗ trợ** PASS.
- Dữ liệu user được bảo toàn hoặc migration theo schema policy PASS.
- Gỡ và cài lại PASS theo chính sách giữ/xóa đã được duyệt.
- Không có lỗi đặc quyền, file lock, dependency/JRE hoặc dữ liệu hỏng chưa giải quyết.
- Có phương án backup/rollback đã kiểm chứng nếu upgrade gặp sự cố.

Nếu người dùng có thể nâng cấp trực tiếp từ nhiều bản cũ (chẳng hạn 1.0 → 3.0, 2.5 → 3.0), **không chỉ test từ bản ngay trước**. Chọn ma trận phiên bản và schema dựa trên chính sách hỗ trợ thật của sản phẩm.

## 10. Các lỗi thường gặp

| Lỗi / hiểu nhầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Cho rằng tạo được `msi`/`deb` là đã test được nâng cấp | Chưa thử gỡ bản cũ, registry/package manager, file state | Test trên máy/VM đã có bản cũ |
| Test nâng cấp trên máy sạch | Không có dữ liệu hay bản trước để đối chiếu | Chuẩn bị state thực và snapshot |
| Lưu user data trong thư mục cài đặt | Upgrade/uninstall có thể ghi đè/xóa | Dùng thư mục dữ liệu user độc lập |
| Gỡ ứng dụng rồi mặc định xóa hết `AppData`/`HOME` | Dễ xóa dữ liệu người dùng không được phép | Chỉ dọn đúng phạm vi theo policy |
| Coi `--app-version` là version của data schema | Không biết migration cần thiết hay không | Định nghĩa `schemaVersion` riêng trong dữ liệu |
| Thay Windows `--win-upgrade-uuid` mỗi release | Có thể khiến package không được nhận là đường nâng cấp | Dùng UUID ổn định riêng sản phẩm |
| Thay `--linux-package-name` khi update | Package manager có thể nhận là gói khác | Giữ định danh package hoặc có kế hoạch chuyển đổi |
| Đổi per-user thành per-machine không có kế hoạch | Cài đặt trùng, quyền/file data khác | Test chuyển scope và profile riêng |
| Chỉ kiểm tra file tồn tại | File có thể bị reset/hỏng/không tương thích | So dữ liệu logic và backup |
| Migration trực tiếp không backup | Dễ mất dữ liệu khi I/O lỗi | Backup + giao dịch/atomic write phù hợp |
| Mặc định `pkgutil --forget` gỡ mọi file | Lưu lại files đã cài trên macOS | Dùng quy trình gỡ theo loại gói thực tế |
| Dùng `apt purge` mà không hiểu phạm vi | Có thể xóa config package không mong muốn | Đọc chính sách distro và thử trên VM |
| Thử uninstall trên máy làm việc | Rủi ro ảnh hưởng người dùng thật | Test trên VM/sandbox, snapshot |
| Tưởng hai app images v1/v2 bằng test installer upgrade | Không kiểm tra backend native | Tách smoke test image khỏi kiểm thử native |
| Test bằng tài khoản admin nhưng phát hành cho user thường | Sai khác quyền và vị trí profile | Test scope với user thường |
| Đăng log data thật/secret trong QA | Rò rỉ thông tin | Dùng dữ liệu test và redact |
| Dựa hoàn toàn vào thư mục mặc định của OS | Chính sách hoặc config có thể đổi đường dẫn | Kiểm tra path thực theo API/platform |

## 11. Câu hỏi ôn tập có đáp án

**Câu 1.** `jpackage --type app-image` đã đủ để kết luận uninstall MSI sẽ xóa đúng file chưa?  
**Đáp án:** Chưa. App image kiểm tra launcher/runtime; uninstall native phải thử bằng chính installer và OS phù hợp.

**Câu 2.** Vì sao không nên ghi user data vào `Program Files` hoặc trong `.app` bundle?  
**Đáp án:** Những thư mục đó do quá trình cài/nâng cấp/gỡ quản lý, có thể không cho user ghi và bị thay thế/xóa. User data nên lưu ở vị trí người dùng phù hợp.

**Câu 3.** Vị trí dữ liệu user thường dùng trên Windows, Linux, macOS là gì?  
**Đáp án:** Windows `%LOCALAPPDATA%\LessonDesk`, Linux `$XDG_DATA_HOME/lessondesk` (mặc định `~/.local/share/lessondesk`), macOS không sandboxed `~/Library/Application Support/LessonDesk`.

**Câu 4.** Để upgrade Windows MSI cùng sản phẩm, ngoài tăng version cần chú ý gì?  
**Đáp án:** Giữ định danh sản phẩm/chuỗi nâng cấp ổn định, ví dụ `--win-upgrade-uuid`, phạm vi per-user/per-machine và quy tắc upgrade của backend.

**Câu 5.** Nếu v2 đọc được file cũ nhưng mất tùy chọn `theme=dark` thì bài test retention có PASS không?  
**Đáp án:** Không. Dữ liệu cần giữ phải còn **đúng giá trị**, không chỉ file còn tồn tại.

**Câu 6.** Vì sao nên có `schemaVersion` riêng?  
**Đáp án:** Version ứng dụng và version cấu trúc lưu trữ thay đổi theo nhịp khác nhau; migration cần biết schema thực tế.

**Câu 7.** `pkgutil --forget` có phải lệnh uninstall file của một PKG macOS không?  
**Đáp án:** Không. Nó chỉ quên receipt; không thay thế quy trình xóa file đúng của package.

**Câu 8.** Khi uninstaller xóa file mã ứng dụng nhưng giữ `prefs.properties` theo chính sách, đó có phải bug?  
**Đáp án:** Không, nếu chính sách công bố là giữ user data để cài lại. Phải kiểm tra cả dữ liệu còn nguyên và app được gỡ sạch.

**Câu 9.** Khi migration làm đổi schema, có nên yêu cầu hash file mới bằng hash file cũ không?  
**Đáp án:** Không. Hash có thể đổi có chủ đích; cần kiểm tra giá trị nghiệp vụ, backup và tính toàn vẹn.

**Câu 10.** Vì sao cần test cả người dùng thường và quyền admin?  
**Đáp án:** Phạm vi cài đặt, thư mục dữ liệu, quyền ghi và profile có thể khác, gây sai kết quả nếu chỉ test bằng một account đặc quyền.

## 12. Tổng kết và nguồn tham khảo hiện hành

**Chuỗi kiểm thử đúng** là: **build installer đúng OS → snapshot máy sạch → cài v1 → tạo state người dùng → backup → nâng cấp v2 → kiểm tra migration và launcher → gỡ → kiểm tra chính sách retention → cài lại và đọc dữ liệu**.

Ba bài học quan trọng nhất:

1. `jpackage` tạo bộ gói/installer, nhưng **không tự thiết kế chính sách lưu/xóa dữ liệu nghiệp vụ**.
2. **Dữ liệu người dùng phải có vòng đời riêng** so với mã ứng dụng đã cài; cần kiểm thử cả giá trị và schema.
3. **Không đồng nhất app image test với native installer test**; dùng VM/sandbox và OS package manager/installer thực để kiểm chứng nâng cấp/gỡ.

Các bước và API trong bài dùng Java 17+ và `jpackage` ổn định từ Java 16, không phụ thuộc vào công cụ incubating cũ.

**Tài liệu chính thức:**

- [Oracle Java SE 25 — The jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): `--type`, `--app-version`, `--install-dir`, `--win-per-user-install`, `--win-upgrade-uuid`, `--linux-package-name` và ràng buộc theo OS.
- [Oracle Java SE 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): app image và vị trí cài mặc định theo nền tảng.
- [Oracle Java SE 25 — Manage the Installation of Your Application](https://docs.oracle.com/en/java/javase/25/jpackage/manage-installation.html): vị trí cài đặt và lối tắt/khả năng tùy biến native installer.
- [Microsoft Learn — KNOWNFOLDERID](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid): `FOLDERID_LocalAppData` và `FOLDERID_RoamingAppData`.
- [freedesktop.org — Desktop Menu Specification: Install Locations](https://specifications.freedesktop.org/menu/latest/locations.html): `XDG_DATA_HOME`, `XDG_CONFIG_HOME` và đường dẫn mặc định.
- [Apple Developer — applicationSupportDirectory](https://developer.apple.com/documentation/foundation/url/applicationsupportdirectory): thư mục Application Support của ứng dụng macOS.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` chính thức từ Java 16.
