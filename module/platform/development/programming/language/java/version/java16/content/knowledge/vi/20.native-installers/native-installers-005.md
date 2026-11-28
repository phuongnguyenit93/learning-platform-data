# Cấu hình --install-dir và dữ liệu ứng dụng theo quyền người dùng

Khi đóng gói ứng dụng Java bằng **jpackage**, cần xác định rõ hai vị trí: nơi cài các file chương trình và nơi ứng dụng lưu dữ liệu khi chạy. Tùy chọn **--install-dir** điều chỉnh thư mục cài đặt trên các nền tảng và loại package hỗ trợ tùy chọn này. Nó không phải cấu hình cho thư mục chứa dữ liệu người dùng, cấu hình, cache hay log.

Phân biệt hai vùng này giúp ứng dụng nâng cấp an toàn, không làm mất dữ liệu khi gỡ cài đặt và không yêu cầu người dùng có quyền quản trị chỉ để lưu tùy chọn cá nhân. Windows, Linux và macOS có quy ước riêng cho cài đặt per-user, cài đặt toàn máy và thư mục dữ liệu.

Trong module Java 16, **jpackage** là công cụ đóng gói đã được hoàn thiện và tiếp tục phù hợp với quy trình phát hành Java hiện đại. Bài này tập trung vào **--install-dir**, lựa chọn phạm vi cài đặt và cách tổ chức dữ liệu theo quyền người dùng hoặc toàn hệ thống. Các hướng dẫn chỉ sử dụng cơ chế nền tảng còn được hỗ trợ; không lưu dữ liệu thay đổi thường xuyên bên trong thư mục cài chương trình.

## 1. Phân biệt thư mục cài đặt và thư mục dữ liệu

Một ứng dụng desktop thường có ít nhất hai nhóm file:

| Nhóm | Ví dụ | Đặc điểm |
|---|---|---|
| File chương trình | Launcher, JAR, runtime image, thư viện, icon và resource bất biến | Được cài đặt hoặc thay thế khi nâng cấp ứng dụng. |
| Dữ liệu người dùng | Cấu hình cá nhân, database cục bộ, file làm việc, trạng thái phiên, cache và log | Được tạo hoặc thay đổi trong lúc ứng dụng chạy; thường thuộc quyền của người dùng. |

Thư mục cài đặt nên chứa các file do bộ cài quản lý. Thư mục dữ liệu nên nằm ở vị trí dành riêng cho ứng dụng trong profile người dùng hoặc vùng dữ liệu toàn hệ thống.

Ví dụ, ứng dụng InventoryApp có thể được cài tại một vị trí dưới /opt trên Linux, trong Program Files trên Windows hoặc dưới Applications trên macOS. Cấu hình cá nhân và dữ liệu làm việc của từng người dùng nên nằm trong thư mục dữ liệu riêng của họ.

Không nên lưu database, file cấu hình người dùng hoặc file tải xuống vào thư mục cài đặt. Package manager có thể thay thế file ở đó khi nâng cấp; quyền ghi cũng thường bị giới hạn đối với người dùng thông thường.

## 2. --install-dir có vai trò gì?

Tùy chọn **--install-dir** chỉ định thư mục cài đặt cơ sở cho các loại package và nền tảng hỗ trợ tùy chọn này. Ví dụ trên Linux:

~~~bash
jpackage \
  --type deb \
  --name InventoryApp \
  --app-image build/app-image/InventoryApp \
  --install-dir /opt \
  --dest dist
~~~

Trong ví dụ, /opt là thư mục cài đặt cơ sở được yêu cầu. Đường dẫn cuối cùng của ứng dụng còn phụ thuộc cách jpackage tạo package và tên ứng dụng; hãy kiểm tra nội dung package hoặc cài thử để xác nhận vị trí thực tế.

Các điểm cần nhớ:

- **--install-dir** điều khiển vị trí file chương trình được cài, trong phạm vi nền tảng và loại package hỗ trợ.
- Nó không đặt user.home, APPDATA, XDG_DATA_HOME hay thư mục dữ liệu ứng dụng.
- Nó không tự tạo chính sách phân quyền cho database hoặc file cấu hình do ứng dụng sinh ra.
- Khả năng áp dụng và ý nghĩa chi tiết có thể khác theo OS, loại installer và phiên bản JDK. Kiểm tra **jpackage --help** của đúng JDK trên runner đích.

Không nên giả định **--install-dir** có cùng hành vi trên EXE, MSI, DEB, RPM, DMG và PKG. Hãy xác nhận loại package cụ thể và kiểm tra artifact sau khi cài.

## 3. Chọn cài đặt per-user hay per-machine

**Per-user** cài ứng dụng cho một tài khoản người dùng. Cách này thường giảm nhu cầu quyền quản trị và phù hợp với ứng dụng desktop cá nhân.

**Per-machine** cài ứng dụng dùng chung trên máy. Cách này phù hợp khi bộ phận IT quản lý thiết bị, nhiều tài khoản cần dùng cùng ứng dụng hoặc ứng dụng là dịch vụ hệ thống. Cài đặt thường cần quyền quản trị.

| Tiêu chí | Per-user | Per-machine |
|---|---|---|
| Phạm vi | Một tài khoản người dùng | Toàn máy hoặc nhiều tài khoản |
| Quyền cài đặt | Thường không cần quyền quản trị | Thường cần quyền quản trị |
| File chương trình | Nằm trong vùng cài đặt của người dùng | Nằm trong vùng cài đặt hệ thống |
| Dữ liệu cá nhân | Profile của người dùng đó | Vẫn nên lưu riêng trong profile từng người dùng |
| Dữ liệu chia sẻ | Không phải mục tiêu chính | Có thể dùng vùng dữ liệu toàn hệ thống với ACL/quyền phù hợp |
| Quản trị | Người dùng tự cài và cập nhật | IT hoặc công cụ quản trị phần mềm có thể triển khai |

Cài ứng dụng toàn máy không có nghĩa mọi dữ liệu ứng dụng phải được chia sẻ. Nếu nhiều tài khoản cùng chạy ứng dụng, cấu hình và dữ liệu cá nhân vẫn nên tách riêng theo từng tài khoản, trừ khi nghiệp vụ yêu cầu một kho dữ liệu chung.

## 4. Windows: thư mục chương trình và dữ liệu

### Vị trí cài đặt

Với cài đặt toàn máy, ứng dụng thường nằm trong Program Files. Với cài đặt theo người dùng, ứng dụng có thể được cài dưới vùng LocalAppData của người dùng. Vị trí thực tế phụ thuộc loại installer và cấu hình jpackage.

Tùy chọn Windows thường liên quan:

- **--win-per-user-install**: yêu cầu cài đặt theo người dùng cho installer Windows hỗ trợ tùy chọn này.
- **--win-dir-chooser**: cho phép người dùng chọn thư mục cài đặt trong quy trình installer hỗ trợ.
- **--win-menu** và **--win-shortcut**: tạo shortcut/menu theo lựa chọn của ứng dụng và installer.

Ví dụ tạo MSI cài theo người dùng:

~~~powershell
jpackage --type msi --name InventoryApp --app-version 1.4.0 --app-image build\app-image\InventoryApp --win-per-user-install --dest dist
~~~

Tùy chọn **--win-per-user-install** điều khiển phạm vi cài đặt; nó không chỉ định nơi lưu dữ liệu của ứng dụng. Kiểm tra **jpackage --help** và thử MSI trên Windows sạch để xác nhận hành vi của JDK đang dùng.

### Dữ liệu theo người dùng

Windows cung cấp các biến môi trường thường dùng:

- **%LOCALAPPDATA%**: dữ liệu cục bộ của ứng dụng cho người dùng hiện tại, phù hợp với database cục bộ, cache hoặc trạng thái không cần roaming.
- **%APPDATA%**: dữ liệu roaming của người dùng, phù hợp với cấu hình nhỏ cần đi theo profile nếu môi trường tổ chức hỗ trợ roaming.
- **%USERPROFILE%**: thư mục profile của người dùng; không nên tự đặt mọi loại dữ liệu trực tiếp tại đây.
- **%PROGRAMDATA%**: dữ liệu dùng chung toàn máy, thường cần chính sách ACL rõ ràng.

Ví dụ vị trí dữ liệu:

~~~text
%LOCALAPPDATA%\ExampleVendor\InventoryApp\
    database\
    cache\
    state\

%APPDATA%\ExampleVendor\InventoryApp\
    preferences\
~~~

Không lưu database lớn hoặc cache có thể tái tạo trong vùng roaming nếu điều đó làm profile đồng bộ quá nặng. Với dữ liệu dùng chung, có thể cân nhắc **%PROGRAMDATA%\ExampleVendor\InventoryApp**, nhưng cần xác định tài khoản nào được đọc/ghi và tạo ACL thích hợp.

## 5. Linux: thư mục cài đặt và XDG Base Directory

Với DEB/RPM, file chương trình thường được cài vào vùng hệ thống và package manager quản lý vòng đời file. **--install-dir** có thể dùng để chọn thư mục cài đặt cơ sở cho package được hỗ trợ, ví dụ **/opt**. Cài package toàn hệ thống thường cần quyền quản trị.

Đối với dữ liệu người dùng, nên tuân theo XDG Base Directory Specification:

| Biến | Giá trị mặc định nếu chưa đặt | Mục đích |
|---|---|---|
| XDG_CONFIG_HOME | $HOME/.config | Cấu hình người dùng. |
| XDG_DATA_HOME | $HOME/.local/share | Dữ liệu lâu dài của ứng dụng. |
| XDG_CACHE_HOME | $HOME/.cache | Cache có thể tạo lại. |
| XDG_STATE_HOME | $HOME/.local/state | Trạng thái thay đổi theo thời gian, ví dụ log hoặc lịch sử cục bộ. |

Ví dụ:

~~~text
~/.config/inventory-app/       # cấu hình
~/.local/share/inventory-app/  # database và dữ liệu lâu dài
~/.cache/inventory-app/        # cache
~/.local/state/inventory-app/  # trạng thái và log
~~~

Không hardcode đường dẫn /home/ten-nguoi-dung. Dùng biến XDG nếu có và fallback theo giá trị mặc định từ home directory. Tôn trọng quyền truy cập của người dùng hiện tại.

### Dữ liệu toàn hệ thống trên Linux

Với ứng dụng chạy như service hoặc có dữ liệu chia sẻ, các vị trí thường dùng gồm:

- **/etc/<app>**: cấu hình quản trị toàn hệ thống.
- **/var/lib/<app>**: dữ liệu trạng thái lâu dài của service.
- **/var/log/<app>**: log của service nếu không dùng journald hoặc hệ thống log tập trung.
- **/var/cache/<app>**: cache toàn hệ thống có thể tái tạo.

Các thư mục này thuộc phạm vi quản trị hệ thống. Package hoặc service setup cần tạo chúng với owner/group và mode phù hợp. Không cấp quyền ghi rộng cho mọi người dùng chỉ để tránh lỗi permission.

## 6. macOS: Application Support, Preferences và Caches

Trên macOS, ứng dụng dạng bundle thường được đặt trong /Applications khi cài cho toàn máy hoặc vị trí ứng dụng theo người dùng nếu quy trình phân phối cho phép. DMG thường cung cấp bundle để người dùng kéo vào Applications; PKG dùng macOS Installer theo cấu hình package.

Các vùng dữ liệu phổ biến:

| Phạm vi | Vị trí | Mục đích |
|---|---|---|
| Theo người dùng | ~/Library/Application Support/<Vendor>/<App> | Database, file làm việc và dữ liệu lâu dài. |
| Theo người dùng | ~/Library/Preferences | Preferences; có thể dùng Java Preferences API cho thiết lập dạng key/value. |
| Theo người dùng | ~/Library/Caches/<Vendor>/<App> | Cache có thể tạo lại. |
| Theo người dùng | ~/Library/Logs/<App> | Log cục bộ của ứng dụng. |
| Toàn hệ thống | /Library/Application Support/<Vendor>/<App> | Dữ liệu dùng chung cần quyền quản trị và quyền truy cập rõ ràng. |

Không ghi dữ liệu thay đổi thường xuyên vào bên trong bundle .app. Bundle là phần chương trình được phân phối và có thể bị thay thế khi nâng cấp. Người dùng cũng có thể không có quyền ghi vào ứng dụng nằm trong /Applications.

## 7. Ví dụ Java tạo thư mục dữ liệu theo nền tảng

Đoạn mã sau chọn thư mục dữ liệu theo người dùng cho Windows, macOS và Linux. Ví dụ ưu tiên biến môi trường chuẩn, sau đó dùng fallback hợp lý:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class AppDirectories {
    private AppDirectories() {
    }

    public static Path userDataDirectory() throws IOException {
        String os = System.getProperty("os.name").toLowerCase(Locale.ROOT);
        String home = System.getProperty("user.home");
        Path base;

        if (os.startsWith("windows")) {
            String localAppData = System.getenv("LOCALAPPDATA");
            base = localAppData == null || localAppData.isBlank()
                    ? Path.of(home, "AppData", "Local")
                    : Path.of(localAppData);
        } else if (os.contains("mac")) {
            base = Path.of(home, "Library", "Application Support");
        } else {
            String xdgDataHome = System.getenv("XDG_DATA_HOME");
            base = xdgDataHome == null || xdgDataHome.isBlank()
                    ? Path.of(home, ".local", "share")
                    : Path.of(xdgDataHome);
        }

        Path appDirectory = base
                .resolve("ExampleVendor")
                .resolve("InventoryApp");
        return Files.createDirectories(appDirectory);
    }
}
~~~

Phương thức này tạo thư mục nếu chưa tồn tại và trả về đường dẫn. Ứng dụng nên gọi nó khi cần lưu dữ liệu lần đầu, xử lý IOException phù hợp và không giả định người dùng luôn có quyền ghi ở mọi vị trí.

Đây là ví dụ cho vùng dữ liệu lâu dài. Trong ứng dụng hoàn chỉnh, nên tách hàm riêng cho configuration, cache và state để dùng đúng vùng XDG hoặc thư mục tương ứng trên Windows/macOS. Không nên gom tất cả loại dữ liệu vào một thư mục nếu chính sách backup, roaming hoặc retention khác nhau.

## 8. Dùng Java Preferences API cho thiết lập nhỏ

Với các thiết lập dạng key/value như ngôn ngữ, giao diện hoặc tùy chọn người dùng, có thể dùng **java.util.prefs.Preferences**:

~~~java
import java.util.prefs.Preferences;

public final class UserSettings {
    private static final Preferences PREFS =
            Preferences.userNodeForPackage(UserSettings.class);

    private UserSettings() {
    }

    public static String language() {
        return PREFS.get("language", "vi");
    }

    public static void setLanguage(String language) {
        PREFS.put("language", language);
    }
}
~~~

**Preferences.userNodeForPackage** cung cấp node preferences cho người dùng hiện tại. Cách lưu trữ cụ thể phụ thuộc nền tảng và implementation của Java. API này phù hợp cho preferences nhỏ; không dùng thay cho database, file làm việc hoặc kho dữ liệu lớn.

Nếu ứng dụng cần đồng bộ hoặc backup preferences, hãy thiết kế cơ chế export/import riêng thay vì giả định vị trí lưu nội bộ của Preferences là giống nhau trên mọi hệ điều hành.

## 9. Quyền ghi và bảo vệ dữ liệu

Quyền truy cập cần phù hợp với phạm vi dữ liệu:

- Dữ liệu cá nhân chỉ nên cho tài khoản sở hữu và các tiến trình được phép truy cập.
- Dữ liệu toàn hệ thống cần owner/group hoặc ACL xác định; chỉ cấp quyền ghi cho tài khoản hoặc service cần thiết.
- File chương trình trong thư mục cài đặt nên được bảo vệ khỏi việc sửa đổi bởi người dùng thông thường.
- Cache có thể tái tạo, nhưng vẫn không nên cho người dùng khác ghi tùy tiện nếu có nguy cơ thay thế file hoặc chèn nội dung độc hại.
- Secret như token, khóa API hoặc thông tin xác thực cần kho lưu trữ an toàn của nền tảng; không xem thư mục cấu hình thông thường là secret vault.

Trên Linux/macOS, có thể dùng quyền POSIX phù hợp khi tạo file hoặc thư mục. Trên Windows, cần dùng ACL của NTFS và không giả định permission POSIX áp dụng giống nhau. Java NIO hỗ trợ một số thuộc tính permission theo provider; kiểm tra khả năng hỗ trợ trước khi dựa vào chúng.

Không giải quyết lỗi ghi file bằng cách cấp quyền 777 cho thư mục cài đặt hoặc dữ liệu. Hãy xác định đúng tài khoản chạy ứng dụng và cấp quyền tối thiểu cần thiết.

## 10. Dữ liệu của service và dữ liệu của desktop app

Ứng dụng desktop thường chạy dưới tài khoản đăng nhập. Dữ liệu cá nhân nên nằm trong profile người dùng để các tài khoản không ghi đè dữ liệu của nhau.

Service hoặc daemon thường chạy bằng tài khoản dịch vụ riêng. Dữ liệu cần tồn tại qua lần restart có thể đặt trong vùng trạng thái toàn hệ thống, chẳng hạn /var/lib/<app> trên Linux hoặc vùng dữ liệu chương trình tương ứng trên Windows/macOS. Cấu hình quản trị nên được tách khỏi dữ liệu runtime nếu cần phân quyền khác nhau.

Không dùng home directory của người cài đặt để lưu dữ liệu của service. Installer có thể chạy dưới quyền administrator/root, còn service chạy dưới tài khoản khác; nếu lưu nhầm vào profile của người cài, service có thể không đọc được hoặc dữ liệu bị gắn với tài khoản sai.

## 11. Nâng cấp và gỡ cài đặt mà không làm mất dữ liệu

Tách file chương trình và dữ liệu cho phép cập nhật installer mà vẫn giữ thông tin người dùng. Tuy nhiên, việc giữ dữ liệu cần được thiết kế rõ ràng:

1. **Lưu dữ liệu ngoài install directory:** package manager có thể thay thế hoặc xóa file trong thư mục cài đặt.
2. **Giữ schema có phiên bản:** khi database thay đổi, thực hiện migration có kiểm soát và backup trước thao tác rủi ro.
3. **Ghi file an toàn:** với file cấu hình quan trọng, ghi vào file tạm cùng filesystem rồi thay thế nguyên tử khi nền tảng hỗ trợ.
4. **Không xóa dữ liệu cá nhân mặc định:** uninstall nên gỡ file chương trình; chỉ xóa dữ liệu người dùng khi có chính sách rõ ràng hoặc người dùng xác nhận.
5. **Xử lý dữ liệu dùng chung riêng:** nếu gỡ cài đặt toàn máy, xác định service, tài khoản và các ứng dụng khác còn phụ thuộc vùng dữ liệu chung hay không.
6. **Có phương án backup/restore:** cung cấp cách sao lưu hoặc xuất dữ liệu quan trọng trước khi nâng cấp/gỡ cài đặt.

Không dựa vào việc installer luôn chạy dưới cùng tài khoản với người dùng. Bước cài đặt nâng quyền có thể chạy dưới administrator hoặc root, nên không phù hợp để tự ý tạo, sửa hoặc xóa dữ liệu trong profile của một người dùng cụ thể.

## 12. Bảng lựa chọn nhanh

| Nhu cầu | Windows | Linux | macOS |
|---|---|---|---|
| File chương trình toàn máy | Program Files | Vùng cài đặt package, có thể chọn base bằng --install-dir khi hỗ trợ | /Applications hoặc vị trí do installer chọn |
| File chương trình theo người dùng | Vùng cài đặt user-level; xem --win-per-user-install | Thường dùng gói/triển khai riêng theo user nếu hệ thống cho phép | Có thể cài bundle trong vùng ứng dụng của user |
| Cấu hình cá nhân | %APPDATA% hoặc %LOCALAPPDATA% | $XDG_CONFIG_HOME | ~/Library/Preferences hoặc Application Support tùy loại dữ liệu |
| Dữ liệu lâu dài cá nhân | %LOCALAPPDATA% | $XDG_DATA_HOME | ~/Library/Application Support |
| Cache cá nhân | %LOCALAPPDATA% | $XDG_CACHE_HOME | ~/Library/Caches |
| Dữ liệu toàn máy | %PROGRAMDATA% | /var/lib, /etc, /var/log theo mục đích | /Library/Application Support, /Library/Logs |

Đây là các vị trí theo quy ước nền tảng. Hãy kiểm tra biến môi trường, quyền thực tế và chính sách của tổ chức trước khi sử dụng.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ứng dụng không lưu được cấu hình sau cài | Cố ghi vào thư mục cài đặt được bảo vệ | Chuyển cấu hình sang vùng dữ liệu người dùng. |
| Nâng cấp làm mất database | Database đặt trong install directory bị thay thế | Di chuyển dữ liệu lâu dài ra vùng user data hoặc system data. |
| Người dùng A đọc được dữ liệu riêng của B | Dữ liệu nhiều user đặt chung và quyền quá rộng | Tách thư mục theo user và giới hạn ACL/mode. |
| Service không đọc được dữ liệu sau cài | Dữ liệu được tạo trong home của administrator/root | Dùng vùng dữ liệu service và gán owner/group đúng. |
| --install-dir không thay đổi nơi lưu cấu hình | Nhầm install directory với app data directory | Tạo đường dẫn dữ liệu trong ứng dụng theo quy ước OS. |
| Gỡ ứng dụng xóa nhầm file người dùng | Uninstall script xóa toàn bộ vùng dữ liệu không phân biệt | Tách file package và data; yêu cầu xác nhận trước khi xóa dữ liệu cá nhân. |
| Cache đồng bộ qua roaming profile gây chậm | Lưu cache vào vùng roaming | Chuyển cache sang vùng local/cache phù hợp. |

## 14. Quy trình kiểm thử

Trước khi phát hành, kiểm tra cả vị trí cài đặt lẫn vùng dữ liệu:

1. Cài ứng dụng theo phạm vi per-user hoặc per-machine dự kiến.
2. Xác nhận launcher và runtime nằm trong vùng cài đặt đúng.
3. Chạy ứng dụng bằng tài khoản thường và tạo cấu hình, dữ liệu, cache.
4. Đăng nhập bằng tài khoản khác để xác nhận dữ liệu cá nhân được tách biệt.
5. Kiểm tra quyền đọc/ghi của thư mục dữ liệu và thư mục chương trình.
6. Nâng cấp từ phiên bản trước và xác nhận dữ liệu còn nguyên hoặc được migration đúng.
7. Gỡ cài đặt và xác nhận file chương trình được gỡ, dữ liệu được giữ/xóa theo chính sách.
8. Với service, kiểm tra bằng đúng tài khoản dịch vụ sau khi restart máy hoặc service.

Kiểm tra trên máy sạch hoặc máy ảo có baseline hệ điều hành được hỗ trợ. Không chỉ kiểm tra bằng tài khoản administrator vì tài khoản này có thể che khuất lỗi quyền mà người dùng thông thường sẽ gặp.

## 15. Cách áp dụng trong ứng dụng Java hiện đại

- Dùng **--install-dir** để điều chỉnh vị trí cài chương trình trên loại package và nền tảng hỗ trợ; xác nhận kết quả bằng cách cài thử.
- Trên Windows, phân biệt **--win-per-user-install** với thư mục dữ liệu trong AppData.
- Trên Linux, tuân theo XDG cho dữ liệu cá nhân và dùng vùng /etc, /var/lib, /var/log cho dữ liệu quản trị/service theo đúng mục đích.
- Trên macOS, đặt dữ liệu người dùng trong Library và giữ bundle ứng dụng không chứa dữ liệu thay đổi.
- Dùng Java Preferences API cho thiết lập nhỏ; dùng file hoặc database riêng cho dữ liệu lớn.
- Tách cấu hình, dữ liệu lâu dài, cache và log vì chúng có chính sách backup/retention khác nhau.
- Không yêu cầu quyền quản trị để ghi dữ liệu cá nhân; giới hạn quyền cho dữ liệu toàn hệ thống.
- Thiết kế nâng cấp và gỡ cài đặt để không xóa dữ liệu người dùng ngoài ý muốn.

**--install-dir** quản lý vị trí của chương trình được cài đặt. Dữ liệu phát sinh khi chạy cần được đặt riêng theo người dùng hoặc toàn hệ thống, dựa trên quy ước và quyền của Windows, Linux hoặc macOS. Tách hai vùng này giúp bộ cài dễ quản trị, ứng dụng an toàn hơn khi chạy bằng tài khoản thường và dữ liệu được bảo toàn qua các lần nâng cấp.
