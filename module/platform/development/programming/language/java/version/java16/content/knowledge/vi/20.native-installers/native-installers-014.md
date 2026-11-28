# Bảo toàn dữ liệu người dùng khi nâng cấp hoặc gỡ ứng dụng

Ứng dụng Java được đóng gói bằng `jpackage` có thể được cài đặt, nâng cấp và gỡ bằng installer native của hệ điều hành. Để dữ liệu người dùng tồn tại qua các thao tác này, hãy lưu dữ liệu ở thư mục dành riêng cho người dùng và tách biệt với thư mục cài đặt ứng dụng.

`jpackage` đóng gói chương trình và runtime; nó không tự thiết kế chính sách lưu trữ, sao lưu hoặc chuyển đổi dữ liệu nghiệp vụ. Ứng dụng cần quy tắc riêng cho vị trí dữ liệu, phiên bản schema, migration, rollback và hành vi khi gỡ.

## 1. Phân biệt thư mục cài đặt và dữ liệu người dùng

Thư mục cài đặt chứa thành phần do nhà phát triển phát hành: launcher, file thực thi, JAR hoặc module, runtime Java đi kèm, thư viện native và tài nguyên của bản phát hành.

Dữ liệu người dùng là nội dung được tạo hoặc thay đổi trong quá trình sử dụng: database cục bộ, tài liệu, dự án, bản xuất, cấu hình cá nhân, trạng thái làm việc, lịch sử và metadata.

Không lưu dữ liệu quan trọng trong thư mục cài đặt. Installer có thể thay thế hoặc xóa thư mục này khi nâng cấp; thư mục có thể chỉ cho phép quản trị viên ghi; nhiều tài khoản có thể dùng chung một bản cài đặt.

| Thành phần | Vị trí nên dùng |
|---|---|
| JAR, launcher, runtime | Thư mục cài đặt do installer quản lý |
| Dữ liệu riêng của người dùng | Thư mục data riêng của tài khoản đó |
| Cấu hình cá nhân | Thư mục config của người dùng |
| Cache có thể tạo lại | Thư mục cache của người dùng |
| Tài liệu do người dùng tạo | Vị trí người dùng chọn hoặc thư mục tài liệu phù hợp |
| Secret, token, mật khẩu | Kho lưu credential của hệ điều hành |

Dữ liệu người dùng phải tiếp tục tồn tại khi thư mục cài đặt bị thay thế hoặc xóa.

## 2. Vì sao nâng cấp có thể làm mất dữ liệu?

Các lỗi thiết kế thường gặp:

- Ghi database vào thư mục cạnh file JAR hoặc launcher.
- Dùng thư mục làm việc hiện tại làm nơi lưu file.
- Ghi đè file cấu hình người dùng bằng cấu hình mặc định mỗi lần cài.
- Đóng gói dữ liệu đang chạy vào installer rồi thay thế dữ liệu hiện có khi nâng cấp.
- Xóa toàn bộ thư mục ứng dụng mà không phân biệt file chương trình với dữ liệu.
- Thay đổi cấu trúc database mà không sao lưu hoặc migration.

Ví dụ không nên dùng:

```java
Path database = Path.of("data", "inventory.db");
```

Đường dẫn tương đối phụ thuộc current working directory. Khi launcher được mở từ shortcut, terminal hoặc thư mục khác, ứng dụng có thể ghi dữ liệu vào các vị trí khác nhau. Nếu đường dẫn này nằm trong application image, installer còn có thể thay thế nó khi nâng cấp.

Hãy xác định thư mục data ổn định theo tài khoản và nền tảng. Không gắn thư mục đó với version ứng dụng, vì bản mới cần tìm được dữ liệu của bản cũ.

## 3. Vị trí lưu dữ liệu theo hệ điều hành

Mỗi hệ điều hành có quy ước riêng cho dữ liệu ứng dụng. Với dữ liệu riêng của một tài khoản, có thể dùng các vị trí sau:

| Hệ điều hành | Dữ liệu ứng dụng | Cấu hình | Cache |
|---|---|---|---|
| Windows | %LOCALAPPDATA%/Vendor/App | %APPDATA%/Vendor/App hoặc LocalAppData tùy nhu cầu | %LOCALAPPDATA%/Vendor/App/Cache |
| macOS | ~/Library/Application Support/App | ~/Library/Preferences hoặc Application Support | ~/Library/Caches/App |
| Linux | $XDG_DATA_HOME/app hoặc ~/.local/share/app | $XDG_CONFIG_HOME/app hoặc ~/.config/app | $XDG_CACHE_HOME/app hoặc ~/.cache/app |

Một số điểm cần chú ý:

- Windows %APPDATA% thường dành cho dữ liệu roaming theo hồ sơ người dùng; %LOCALAPPDATA% dành cho dữ liệu cục bộ trên máy. Database lớn hoặc cache thường phù hợp với LocalAppData hơn.
- macOS dùng Application Support cho dữ liệu ứng dụng. Caches dành cho dữ liệu có thể tạo lại; không lưu bản duy nhất của tài liệu người dùng ở đó.
- Linux tuân theo XDG Base Directory Specification. Các biến XDG_DATA_HOME, XDG_CONFIG_HOME, XDG_STATE_HOME và XDG_CACHE_HOME có thể được người dùng tùy chỉnh. Nếu không có, ứng dụng dùng thư mục mặc định trong home.
- Tài liệu do người dùng tạo không nhất thiết thuộc thư mục dữ liệu riêng của ứng dụng. Nếu người dùng chọn vị trí lưu, hãy giữ nguyên vị trí đó và không tự di chuyển khi nâng cấp.

Tên thư mục ứng dụng cần ổn định qua các phiên bản. Có thể dùng tên sản phẩm cùng tên nhà phát hành hoặc một application identifier cố định. Không đổi tên thư mục data chỉ vì tên hiển thị của sản phẩm thay đổi.

## 4. Ví dụ Java tìm thư mục dữ liệu người dùng

Ví dụ sau chọn thư mục data theo quy ước phổ biến của Windows, macOS và Linux. Nó dùng user.home làm fallback và tôn trọng XDG_DATA_HOME khi giá trị này là đường dẫn tuyệt đối.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class AppPaths {
    private AppPaths() {
    }

    public static Path userDataDirectory(String appId) {
        if (appId == null || !appId.matches("[A-Za-z0-9._-]+")
                || appId.equals(".") || appId.equals("..")) {
            throw new IllegalArgumentException("Invalid application id");
        }

        Path home = Path.of(System.getProperty("user.home"));
        String os = System.getProperty("os.name").toLowerCase(Locale.ROOT);

        if (os.contains("win")) {
            String localAppData = System.getenv("LOCALAPPDATA");
            Path base = localAppData == null || localAppData.isBlank()
                    ? home.resolve("AppData").resolve("Local")
                    : Path.of(localAppData);
            return base.resolve(appId);
        }

        if (os.contains("mac")) {
            return home.resolve("Library")
                    .resolve("Application Support")
                    .resolve(appId);
        }

        String xdgDataHome = System.getenv("XDG_DATA_HOME");
        Path base = xdgDataHome != null && !xdgDataHome.isBlank()
                && Path.of(xdgDataHome).isAbsolute()
                ? Path.of(xdgDataHome)
                : home.resolve(".local").resolve("share");

        return base.resolve(appId);
    }

    public static void main(String[] args) throws Exception {
        Path dataDirectory = userDataDirectory("com.example.inventory");
        Files.createDirectories(dataDirectory);

        Path database = dataDirectory.resolve("inventory.db");
        System.out.println(database);
    }
}
```

`appId` nên là định danh ổn định do ứng dụng quy định, không lấy từ input tùy ý của người dùng. Ví dụ tạo thư mục nếu chưa tồn tại. Trong ứng dụng thực tế, cần xử lý IOException, quyền truy cập và trường hợp thư mục không thể tạo.

Đây là ví dụ về thư mục dữ liệu riêng của ứng dụng. Cấu hình, cache và log có thể cần các thư mục riêng theo quy ước nền tảng. Với Linux, nếu ứng dụng lưu trạng thái runtime hoặc log cần tồn tại qua phiên chạy nhưng không phải dữ liệu chính, có thể cân nhắc XDG_STATE_HOME.

## 5. Tách data, config, cache, log và secret

Không gom mọi loại file vào một thư mục rồi xóa hoặc sao lưu như nhau.

| Loại | Ví dụ | Chính sách |
|---|---|---|
| Data | Database, nội dung do người dùng tạo | Bảo toàn qua upgrade; backup trước migration |
| Config | Tùy chọn, endpoint, giao diện | Giữ thiết lập người dùng; hợp nhất có kiểm soát với mặc định mới |
| Cache | Ảnh tạm, dữ liệu tải lại được | Có thể xóa và tạo lại |
| Log/state | Log vận hành, trạng thái tiến trình | Có chính sách dung lượng và thời hạn riêng |
| Secret | Password, access token, private credential | Dùng credential store của hệ điều hành nếu có |

Không lưu secret dạng văn bản thuần trong file cấu hình chỉ vì file nằm trong thư mục riêng của người dùng. Quyền truy cập thư mục giúp hạn chế người dùng khác, nhưng không thay thế kho credential chuyên dụng.

Không dùng cache làm nơi chứa bản duy nhất của dữ liệu. Cache có thể bị xóa bởi người dùng, công cụ dọn dẹp hoặc chính ứng dụng.

## 6. Giữ nguyên dữ liệu khi cài bản nâng cấp

Installer nên thay thế file chương trình trong thư mục cài đặt. Dữ liệu người dùng phải nằm ở vị trí độc lập để quá trình này không ảnh hưởng database, cấu hình hoặc tài liệu.

Quy trình nâng cấp nên có các bước:

1. Xác định thư mục data ổn định của ứng dụng.
2. Đóng các tiến trình đang ghi dữ liệu hoặc lấy khóa phù hợp.
3. Đọc phiên bản schema hiện tại.
4. Tạo backup trước khi thực hiện migration có rủi ro.
5. Chạy các migration cần thiết theo thứ tự.
6. Chỉ ghi nhận schema version mới sau khi migration hoàn tất.
7. Khởi động ứng dụng và xác minh dữ liệu có thể đọc/ghi.
8. Giữ backup theo chính sách retention để có thể phục hồi nếu phát hiện lỗi sau nâng cấp.

Không sao chép database mặc định trong installer đè lên database hiện có. Nếu cần tạo dữ liệu ban đầu, chỉ khởi tạo khi chưa có file data hoặc database chưa được tạo.

## 7. Phân biệt application version và data schema version

Phiên bản ứng dụng và phiên bản cấu trúc dữ liệu có mục đích khác nhau.

- **Application version:** phiên bản sản phẩm được phát hành, ví dụ 2.4.1.
- **Schema version:** phiên bản cấu trúc database hoặc định dạng file, ví dụ 7.

Một bản phát hành có thể chỉ sửa giao diện mà không thay đổi schema. Ngược lại, một bản phát hành có thể cần migration dữ liệu dù thay đổi version ứng dụng rất nhỏ.

Lưu schema version ở nơi có thể kiểm tra đáng tin cậy, ví dụ bảng metadata của database:

```sql
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO app_metadata (key, value)
VALUES ('schema_version', '1');
```

Đây là ví dụ SQL khái quát; cú pháp và chiến lược migration cụ thể phụ thuộc database engine. Không dùng chuỗi version ứng dụng để suy đoán schema hiện tại.

## 8. Migration phải có backup và khả năng phục hồi

Migration chuyển dữ liệu từ schema cũ sang schema mới. Trước khi thay đổi, ứng dụng cần biết dữ liệu đang ở phiên bản nào và migration nào phải chạy.

Một quy trình migration tốt:

- Có phiên bản nguồn và phiên bản đích rõ ràng.
- Thực hiện theo thứ tự, không bỏ qua migration trung gian.
- Có thể phát hiện migration đã hoàn thành.
- Dùng transaction nếu database hỗ trợ và thay đổi nằm trong phạm vi transaction.
- Tạo bản backup hoặc bản sao an toàn trước thay đổi không thể rollback.
- Chỉ cập nhật schema version sau khi mọi bước thành công.
- Có thông báo rõ nếu không thể tiếp tục.

Ví dụ logic:

```java
int currentVersion = database.readSchemaVersion();

if (currentVersion < TARGET_SCHEMA_VERSION) {
    backupService.createBackup(databasePath);

    migrationRunner.migrate(
        database,
        currentVersion,
        TARGET_SCHEMA_VERSION
    );

    // Chỉ cập nhật version sau khi tất cả migration hoàn tất.
    database.writeSchemaVersion(TARGET_SCHEMA_VERSION);
}
```

Đây là pseudocode mô tả thứ tự công việc; API database và migration runner phụ thuộc ứng dụng. Nếu migration có thể chạy lại sau khi tiến trình bị dừng giữa chừng, mỗi bước cần được thiết kế idempotent hoặc có marker trạng thái rõ ràng.

Với dữ liệu dạng file, có thể tạo file mới ở cùng filesystem, ghi và xác minh đầy đủ, rồi thay thế file cũ bằng thao tác rename. ATOMIC_MOVE có thể không được filesystem hỗ trợ; hãy có chiến lược fallback và giữ backup khi không thể thay thế nguyên tử.

## 9. Xử lý khi nâng cấp thất bại hoặc cần quay lại bản cũ

Nâng cấp binary và migration data là hai thay đổi liên quan nhưng không thể luôn rollback cùng lúc. Bản mới có thể đã chuyển database sang schema mà bản cũ không hiểu.

Trước khi phát hành, hãy quyết định:

- Bản cũ có đọc được schema mới không?
- Có cần giữ tương thích ngược trong một giai đoạn không?
- Nếu migration thất bại, có thể rollback transaction hay phải restore backup?
- Nếu người dùng cài lại phiên bản cũ, dữ liệu sẽ ở trạng thái nào?
- Backup được lưu ở đâu, ai có quyền đọc và khi nào được xóa?

Nếu không hỗ trợ downgrade, hãy thông báo rõ trước khi migration không tương thích. Không tự động khôi phục backup cũ mà không cân nhắc dữ liệu mới được tạo sau thời điểm backup; thao tác đó có thể làm mất thay đổi gần đây của người dùng.

## 10. Không ghi đè cấu hình cá nhân khi cập nhật

Một lỗi phổ biến là installer hoặc ứng dụng chép file cấu hình mặc định vào đúng vị trí chứa cấu hình người dùng mỗi lần chạy.

Nên tách:

- Cấu hình mặc định được đóng gói cùng ứng dụng, chỉ đọc.
- Cấu hình tùy chỉnh của người dùng, lưu ngoài thư mục cài đặt.
- Cấu hình mới được thêm ở phiên bản sau, được hợp nhất có kiểm soát.

Khi nâng cấp, ứng dụng có thể đọc mặc định mới rồi áp dụng các giá trị override của người dùng. Nếu cần chuyển đổi cấu trúc config, hãy tạo bản sao trước, ghi file mới và chỉ thay thế sau khi xác minh thành công.

Không xóa các khóa cấu hình không còn được nhận diện nếu chưa có chính sách di trú rõ ràng. Có thể thư viện hoặc plugin của người dùng vẫn cần các khóa đó.

## 11. Nhiều tài khoản người dùng và dữ liệu dùng chung

Nếu ứng dụng được cài một lần cho cả máy, nhiều tài khoản có thể chạy cùng binary nhưng mỗi người cần dữ liệu riêng.

- Database hoặc hồ sơ riêng của từng người dùng nên nằm trong thư mục data của tài khoản đó.
- Không ghi dữ liệu cá nhân vào thư mục cài đặt dùng chung.
- Không dùng một file database duy nhất trong thư mục toàn máy nếu nhiều người có thể ghi đồng thời mà chưa có cơ chế đồng bộ.
- Dữ liệu thật sự dùng chung cần vị trí và quyền truy cập được thiết kế riêng, chẳng hạn dịch vụ hoặc thư mục chia sẻ được quản trị.

Trên Windows, thư mục dữ liệu toàn máy như ProgramData có thể phù hợp với cấu hình hoặc tài nguyên dùng chung được quản trị, nhưng không tự động phù hợp cho hồ sơ riêng của từng tài khoản. Trên Linux, /var/lib dành cho dữ liệu trạng thái của dịch vụ ở cấp hệ thống; không dùng thay cho dữ liệu cá nhân trong home. Trên macOS, dữ liệu dùng chung cấp hệ thống cần được đặt ở vị trí phù hợp và có quyền sở hữu rõ ràng.

Nếu ứng dụng hỗ trợ cả cài đặt per-user và per-machine, hãy kiểm thử cả hai chế độ. Vị trí cài đặt có thể thay đổi, nhưng quy tắc xác định data directory của từng người dùng cần ổn định.

## 12. Gỡ ứng dụng nhưng giữ dữ liệu

Gỡ ứng dụng thường nên xóa file chương trình và thành phần installer đã quản lý. Dữ liệu người dùng cần được giữ lại theo chính sách mặc định nếu người dùng có thể cài lại hoặc cần xuất dữ liệu sau này.

Một quy tắc thực tế:

- Xóa launcher, binary, runtime đi kèm và file thuộc thư mục cài đặt.
- Giữ database, config và nội dung người dùng trong thư mục data riêng.
- Giữ tài liệu do người dùng lưu ở vị trí họ chọn.
- Chỉ xóa cache nếu chính sách sản phẩm cho phép; cache không phải dữ liệu duy nhất.
- Không xóa dữ liệu dùng chung khi ứng dụng khác hoặc tài khoản khác còn sử dụng.

Trên Windows, uninstall MSI thường quản lý file đã cài trong installation directory; dữ liệu nằm ngoài thư mục đó như LocalAppData hoặc Roaming AppData không nên bị xóa chỉ vì uninstall ứng dụng. Trên macOS, xóa bundle ứng dụng khỏi Applications không tự động có nghĩa dữ liệu trong ~/Library/Application Support đã bị xóa. Trên Linux, gỡ package không nên xóa dữ liệu người dùng trong home directory.

Hành vi cụ thể phụ thuộc installer, package manager, script của nhà phát hành và lựa chọn người dùng. Không giả định mọi định dạng native package có cùng semantics. Hãy thử nghiệm uninstall trên từng nền tảng và xác nhận dữ liệu cần giữ vẫn còn.

## 13. Nếu cho phép xóa dữ liệu khi gỡ

Một số sản phẩm cần cung cấp lựa chọn xóa toàn bộ dữ liệu ứng dụng. Đây phải là hành động có chủ đích và mô tả rõ hậu quả.

Thiết kế nên:

1. Mặc định giữ lại dữ liệu quan trọng nếu người dùng không yêu cầu xóa.
2. Hiển thị rõ thư mục và loại dữ liệu sẽ bị xóa.
3. Cho người dùng cơ hội export hoặc backup trước khi xóa.
4. Yêu cầu xác nhận riêng cho thao tác không thể khôi phục.
5. Chỉ xóa thư mục data riêng thuộc application identifier đã xác định.
6. Không xóa file hoặc thư mục người dùng chọn lưu ở nơi khác.
7. Không xóa dữ liệu dùng chung hoặc dữ liệu do ứng dụng khác sở hữu.

Nếu có công cụ cleanup riêng, cần resolve đường dẫn thực tế, xác minh nó nằm dưới thư mục data dành riêng của ứng dụng và xử lý symbolic link/junction cẩn thận. Tránh lệnh xóa đệ quy dựa trên chuỗi đường dẫn ghép từ input không tin cậy.

Uninstaller không nên xóa một thư mục chung chỉ vì tên thư mục có chứa tên sản phẩm. Một thư mục có thể chứa dữ liệu của nhiều phiên bản hoặc nhiều thành phần khác nhau.

## 14. Vai trò và giới hạn của jpackage

`jpackage` tạo application image hoặc native package từ ứng dụng Java. Công cụ hỗ trợ các tùy chọn đóng gói theo nền tảng, nhưng không tự quyết định schema dữ liệu nghiệp vụ, cách backup, migration hay chính sách giữ dữ liệu cá nhân.

Vì vậy:

- Lưu dữ liệu ở vị trí ổn định do ứng dụng xác định.
- Thực hiện migration trong logic ứng dụng hoặc thành phần quản lý dữ liệu có chủ đích.
- Không đặt database người dùng trong thư mục input của jpackage hoặc thư mục cài đặt.
- Không đóng gói một bản database cá nhân vào installer để ghi đè lên dữ liệu hiện có.
- Nếu cần hành vi uninstall riêng theo nền tảng, phải thiết kế và kiểm thử theo package backend; không giả định có một hook cleanup portable áp dụng cho mọi installer.
- Không dùng file resource hoặc file cấu hình installer làm nơi lưu dữ liệu runtime của người dùng.

`jpackage` không thay thế database migration framework, backup service hoặc chính sách vòng đời dữ liệu. Đây là trách nhiệm của ứng dụng và quy trình vận hành.

## 15. Kiểm thử nâng cấp và gỡ ứng dụng

Không chỉ kiểm tra lần cài mới. Dữ liệu có nguy cơ bị mất thường xuất hiện khi chuyển từ phiên bản cũ sang phiên bản mới hoặc khi uninstall.

| Kịch bản | Điều cần xác minh |
|---|---|
| Cài mới | Data directory được tạo đúng và có quyền ghi |
| Nâng cấp không đổi schema | Database và config cũ còn nguyên |
| Nâng cấp có migration | Backup tồn tại, migration hoàn tất, schema version đúng |
| Migration thất bại | Backup được giữ, ứng dụng báo lỗi rõ, không đánh dấu schema mới |
| Khởi động lại sau nâng cấp | Dữ liệu mới đọc/ghi bình thường |
| Gỡ ứng dụng | File chương trình bị gỡ, data được giữ theo chính sách |
| Cài lại | Ứng dụng nhận lại dữ liệu đã giữ |
| Nhiều tài khoản | Mỗi người dùng nhìn thấy đúng hồ sơ của mình |
| Gỡ khi có dữ liệu dùng chung | Không xóa tài nguyên còn được thành phần khác sử dụng |
| Xóa data có xác nhận | Chỉ xóa đúng thư mục thuộc ứng dụng sau khi người dùng đồng ý |

Chạy các kịch bản trên từng loại installer được phát hành. Application image, MSI, DEB/RPM, PKG hoặc DMG không nhất thiết có cùng quy trình cài và gỡ.

## 16. Những lỗi thường gặp

**Lưu database cạnh launcher hoặc JAR.** Installer có thể thay thế hoặc xóa thư mục cài đặt. Hãy dùng data directory riêng.

**Dùng current working directory.** Vị trí này phụ thuộc cách khởi chạy. Xác định đường dẫn ổn định theo hệ điều hành và tài khoản.

**Gắn data directory với version ứng dụng.** Bản mới sẽ không tìm thấy dữ liệu cũ hoặc tạo database mới. Dùng application identifier ổn định và quản lý schema version riêng.

**Ghi đè config người dùng bằng mặc định mới.** Tách default config và user override; hợp nhất có kiểm soát khi nâng cấp.

**Chỉ test cài mới.** Phải test upgrade từ bản đang phát hành, migration thất bại, uninstall và cài lại.

**Nâng schema nhưng không backup.** Có thể khiến bản cũ không đọc được dữ liệu. Backup trước migration và định nghĩa chiến lược rollback.

**Xóa data mặc định khi uninstall.** Người dùng có thể muốn cài lại hoặc xuất dữ liệu sau này. Giữ data theo chính sách rõ ràng và chỉ xóa khi được yêu cầu.

**Xóa thư mục dùng chung.** Có thể làm mất dữ liệu của tài khoản hoặc ứng dụng khác. Xác định quyền sở hữu và phạm vi trước cleanup.

**Cho rằng jpackage tự migration dữ liệu.** jpackage đóng gói ứng dụng; migration là trách nhiệm của ứng dụng hoặc thành phần quản lý dữ liệu.

**Không kiểm tra quyền ghi.** Thư mục cài đặt dùng chung có thể không cho tài khoản thường ghi. Ghi data vào vị trí dành riêng cho người dùng.

## 17. Ghi nhớ

- Tách thư mục cài đặt khỏi dữ liệu người dùng.
- Dùng vị trí phù hợp với Windows, macOS hoặc XDG trên Linux.
- Giữ application identifier và data directory ổn định qua các phiên bản.
- Phân biệt data, config, cache, log/state và secret.
- Tách application version khỏi data schema version.
- Backup trước migration; chỉ đánh dấu schema mới sau khi migration thành công.
- Thiết kế migration có thứ tự, có thể phục hồi và xử lý việc chạy lại an toàn.
- Không ghi đè config cá nhân hoặc database hiện có khi cài nâng cấp.
- Uninstall nên xóa thành phần chương trình và giữ dữ liệu người dùng theo chính sách đã công bố.
- Nếu cung cấp tùy chọn xóa data, phải mô tả phạm vi và yêu cầu xác nhận rõ ràng.
- Không giả định mọi native installer có cùng hành vi giữ/xóa dữ liệu.
- Kiểm thử cài mới, upgrade, migration lỗi, uninstall và cài lại trên từng nền tảng.

Một installer tốt không chỉ cài được ứng dụng mà còn tôn trọng dữ liệu đã được người dùng tạo ra. Khi data directory độc lập với installation directory, migration có backup và uninstall có chính sách rõ ràng, ứng dụng Java có thể được cập nhật hoặc gỡ mà không làm mất dữ liệu ngoài ý muốn.

## Tài liệu tham khảo

- [The jpackage Command – Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html) — các tùy chọn tạo application image và native package.
- [JEP 392 – Packaging Tool](https://openjdk.org/jeps/392) — jpackage trở thành công cụ production-ready trong Java 16.
- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/) — quy ước thư mục data, config, state và cache trên Linux/Unix desktop.
- [Microsoft Known Folders](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid) — các thư mục chuẩn của hồ sơ người dùng Windows.
- [Apple File System Programming Guide – File System Basics](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html) — quy ước thư mục ứng dụng và dữ liệu trên macOS.

