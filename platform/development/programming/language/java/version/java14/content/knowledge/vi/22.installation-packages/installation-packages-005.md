# Tùy chọn cài theo người dùng hoặc toàn máy khi được hỗ trợ bằng `jpackage` (Java 16+)

> **Mục tiêu:** hiểu lựa chọn **per-user** (chỉ tài khoản Windows hiện tại) và **per-machine** (cài ở phạm vi máy), sử dụng đúng `jpackage --win-per-user-install` khi tạo native installer trên Windows, biết đường dẫn mặc định, nhu cầu quyền quản trị và cách kiểm thử. Cần phân biệt **phạm vi cài đặt** với vị trí/thư mục, shortcuts và định dạng đầu ra. Công cụ `jpackage` đã là tính năng **chính thức từ JDK 16**, vẫn được hỗ trợ trong Java hiện hành; dùng JDK 17+ (ví dụ đã kiểm chứng với OpenJDK 24). Không dùng module `jdk.incubator.jpackage` hoặc mẹo JDK 14–15 thời incubating.

## 1. Vì sao phải chọn phạm vi cài đặt?

Với ứng dụng Java desktop được đóng gói bằng `jpackage` thành **native installer**, phạm vi cài đặt ảnh hưởng tới người dùng có thể sử dụng ứng dụng, vị trí lưu **file chương trình**, quyền cần thiết để cài/nâng cấp/gỡ, cũng như phạm vi shortcut và quản lý triển khai.

Hai chế độ cần phân biệt trên **Windows**:

| Đặc tính | Theo người dùng (per-user) | Toàn máy (per-machine) |
|---|---|---|
| Ý nghĩa | Dành cho tài khoản Windows đang cài | Dành cho hệ thống/máy, nhiều tài khoản có thể dùng theo quyền được cấp |
| Cách yêu cầu trong `jpackage` | **Có `--win-per-user-install`** | **Không có `--win-per-user-install`** (mặc định Windows) |
| Vị trí mặc định theo Oracle JDK 25 | `C:\Users\<user>\AppData\Local\<app-name>` (tương đương dưới `%LOCALAPPDATA%`) | `C:\Program Files\<app-name>` (tương đương dưới `%ProgramFiles%`) |
| Quyền khi cài | Thường có thể cài vào phạm vi profile mà không cần nâng quyền | Thường cần quyền quản trị/UAC do ghi vào vị trí chung |
| Phạm vi quản trị/nâng cấp | Gắn với profile từng người dùng | Phù hợp quản lý tập trung ở cấp máy |
| Chạy dưới tài khoản khác | Không tự động được triển khai sang profile khác | Có thể truy cập từ nhiều tài khoản nếu quyền và ứng dụng cho phép |

**Đây là lựa chọn khi build installer**, không phải một đối số mà người dùng chọn lúc chương trình Java `main()` bắt đầu chạy. Không nên cố đoán phạm vi bằng `System.getProperty("user.home")`; thuộc tính đó nói về **profile của tiến trình hiện tại**, không phản ánh chính xác cách package ban đầu được tạo.

**Phân biệt quyền và phạm vi:** “per-user” không bảo đảm tuyệt đối **không xuất hiện UAC** trong mọi môi trường. Policies của công ty, antivirus, chữ ký số, dịch vụ hệ thống, phần mềm khác và lựa chọn tích hợp của package có thể đặt thêm yêu cầu. “Per-machine” cũng không có nghĩa mọi tài khoản đều được quyền truy cập mọi dữ liệu của ứng dụng; phân quyền file và dữ liệu là vấn đề riêng.

## 2. Các lựa chọn chính xác của `jpackage` trên Windows

Cú pháp cần ghi nhớ:

```powershell
# Native MSI cho người dùng hiện tại:
jpackage --type msi ... --win-per-user-install

# Native MSI toàn máy (mặc định):
jpackage --type msi ...

# Có thể thay --type msi bằng --type exe trên Windows:
jpackage --type exe ... --win-per-user-install
```

Các dấu `...` trên đây chỉ là **ký hiệu rút gọn**, không chạy nguyên văn; lệnh đầy đủ có ở mục 4. Theo Oracle, `--win-per-user-install` yêu cầu installer Windows **cài theo người dùng**. Nếu không chỉ định, Windows installer được tạo với chế độ **per-machine**. Cờ này thuộc nhóm **Windows platform options for creating the application package**, không phải tùy chọn chung cho mọi hệ điều hành.

**Đừng suy ra:** thêm `--win-per-user-install` vào `--type app-image` sẽ tạo installer người dùng. `--type app-image` chỉ tạo **thư mục ứng dụng có launcher/runtime**, chưa thực hiện một cài đặt được quản lý qua MSI/EXE. Muốn tác động đến phạm vi cài đặt, hãy tạo **native installer** (`msi` hoặc `exe`) có cờ phù hợp.

### Quy trình quyết định

```text
Bạn cần cài ứng dụng cho ai?
          |
          +-- Một tài khoản Windows
          |      |
          |      +--> --type msi / exe
          |            --win-per-user-install
          |            (mặc định dưới AppData\Local)
          |
          +-- Cả máy / dùng chung
                 |
                 +--> --type msi / exe
                       không thêm --win-per-user-install
                       (mặc định dưới Program Files)
```

Phần này **không** yêu cầu cả hai installer phải được cài trên cùng một máy. Nếu ứng dụng có cùng tên/version/upgrade identity, cài thử hai biến thể trên cùng profile có thể ảnh hưởng tới quá trình phát hiện phiên bản và gỡ cài đặt. Hãy thử trên **hai máy ảo sạch hoặc snapshot riêng**.

## 3. Phạm vi cài khác với thư mục, shortcut và quyền

Các tùy chọn sau hỗ trợ **điều chỉnh trải nghiệm**, nhưng không phải nút chọn phạm vi cài đặt:

| Tùy chọn | Tác dụng | Có tự đổi per-user/per-machine không? |
|---|---|---|
| `--win-per-user-install` | Yêu cầu chế độ cài theo tài khoản hiện tại | **Có**, chính là cờ chọn scope |
| Không truyền cờ trên | Windows installer mặc định theo máy | **Có**, lựa chọn mặc định |
| `--install-dir AppFolder` | Đổi tên/đường dẫn con của vị trí cài đặt theo nền tảng | **Không** |
| `--win-dir-chooser` | Thêm hộp thoại chọn thư mục trong installer Windows | **Không** |
| `--win-shortcut` | Yêu cầu tạo shortcut desktop | **Không** |
| `--win-menu` | Yêu cầu đưa ứng dụng vào Start Menu | **Không** |
| `--win-menu-group GroupName` | Chọn nhóm Start Menu (cần `--win-menu` để hữu ích) | **Không** |
| `--win-shortcut-prompt` | Cho người cài quyết định shortcut khi kết hợp tùy chọn liên quan | **Không** |
| `--name`, `--app-version` | Tên và phiên bản gói | **Không** |

**`--install-dir` không phải là cách thay thế cờ scope.** Theo tài liệu `jpackage`, trên Windows nó chỉ định **đường dẫn con tương đối** dưới vị trí cài theo Windows, còn trên Linux/macOS có thể dùng đường dẫn cài tuyệt đối. Ví dụ `--install-dir Company\ScopeDemoApp` không tự cho phép user không có quyền quản trị ghi vào `Program Files`, và cũng không chuyển installer từ per-machine sang per-user.

Tương tự, `--win-dir-chooser` chỉ mở UI chọn **vị trí**. Nó **không tự cấp quyền thư mục** và không làm cho package per-machine trở thành per-user. Cần kiểm thử luồng UAC, quyền ghi, shortcut và uninstall theo từng chế độ.

### Quyền administrator trong thực tế

- Per-machine thường ghi vào `Program Files` và cấu hình cài đặt chung; đây là vị trí hệ thống nên **thường** yêu cầu nâng quyền.
- Per-user thường ghi vào `%LOCALAPPDATA%` của người cài, nên **thường** chạy được với tài khoản không có admin khi thiết kế chỉ dùng tài nguyên ở phạm vi user.
- Cài một launcher Java vào AppData **không** cho phép bỏ qua mọi chính sách bảo mật, GPO, AppLocker/WDAC hoặc quy trình cấp phép nội bộ.
- Nếu ứng dụng muốn cài service chạy nền, driver, firewall rule hoặc ghi HKLM, **không mặc định** các tác vụ đó sẽ khả thi chỉ vì bật `--win-per-user-install`. Thiết kế deployment cần được đánh giá riêng.

## 4. Ví dụ chuẩn: tạo hai installer thay thế từ cùng một Java JAR

Ví dụ dùng **ứng dụng Java 17+ cực nhỏ** và hai cách đóng gói trên Windows. Mã Java, JAR và app image đã được biên dịch/chạy trên OpenJDK 24 Windows. **Chưa tạo MSI thật trong môi trường kiểm chứng này do thiếu toolchain WiX**; các lệnh MSI theo cú pháp được tài liệu `jpackage` hiện hành hỗ trợ và cần chạy trên máy Windows có WiX thích hợp.

### 4.1. Mã nguồn Java độc lập

Tạo file **`src\ScopeDemoApp.java`** chứa:

```java
public final class ScopeDemoApp {
    public static void main(String[] args) {
        System.out.println("application=ScopeDemoApp");
        System.out.println("args=" + args.length);
    }
}
```

Chương trình không tự biết nó được cài theo user hay machine; nó chỉ kiểm tra launcher có chạy được. Phạm vi là **thuộc tính của package được tạo**, không phải của bytecode Java.

**Stdout xác định khi chạy JAR hay launcher không truyền tham số:**

```text
application=ScopeDemoApp
args=0
```

Đoạn trên đã được kiểm tra bằng `java -jar` và launcher `jpackage --type app-image` trên Windows.

### 4.2. Build JAR và hai biến thể MSI

Các câu lệnh dưới đây dành cho **Windows PowerShell**, chạy trong thư mục dự án **sạch**. Dấu nháy ngược cuối dòng là line continuation của PowerShell, không dùng nguyên xi trên Bash.

```powershell
# Chạy trong Windows PowerShell, tại thư mục dự án mới.
New-Item -ItemType Directory -Force -Path `
    src,classes,input,dist-user,dist-machine | Out-Null

# Lưu code Java ở mục 4.1 vào src\ScopeDemoApp.java.
javac -encoding UTF-8 -d classes src\ScopeDemoApp.java
jar --create --file input\ScopeDemoApp.jar `
    --main-class ScopeDemoApp -C classes .

# Kiểm chứng JAR trước khi tạo installer:
java -jar input\ScopeDemoApp.jar

# PHƯƠNG ÁN A: Build MSI cho một tài khoản Windows.
jpackage --type msi `
    --name ScopeDemoApp `
    --input input `
    --main-jar ScopeDemoApp.jar `
    --main-class ScopeDemoApp `
    --app-version 1.0.0 `
    --dest dist-user `
    --win-per-user-install `
    --win-menu `
    --win-shortcut

# PHƯƠNG ÁN B: Build MSI theo phạm vi toàn máy.
# Đây là lựa chọn THAY THẾ A, không cài cả hai cùng tên/version.
jpackage --type msi `
    --name ScopeDemoApp `
    --input input `
    --main-jar ScopeDemoApp.jar `
    --main-class ScopeDemoApp `
    --app-version 1.0.0 `
    --dest dist-machine `
    --win-menu `
    --win-shortcut
```

Cả hai phương án đều sử dụng **chính JAR đầu vào**. Hai biến thể khác nhau ở phạm vi package, không khác mã nguồn Java:

- **Phương án A (per-user):** có `--win-per-user-install`. Installer sẽ yêu cầu cài ở phạm vi user, vị trí mặc định dưới `%LOCALAPPDATA%`.
- **Phương án B (per-machine):** **không có** cờ đó. Installer sẽ được tạo theo phạm vi toàn máy, vị trí mặc định dưới `%ProgramFiles%`.

Hai lệnh là **hai lựa chọn để build/QA**, **không phải chỉ dẫn phải cài cả hai cùng lúc**. `--win-menu` và `--win-shortcut` nhằm minh họa các tích hợp Start Menu/Desktop; chúng không xác định phạm vi cài. `--app-version 1.0.0` là phiên bản ứng dụng, **không** phải phiên bản JDK.

**Lưu ý môi trường:** tạo `msi`/`exe` trên Windows thường cần **WiX Toolset** tương thích phiên bản JDK đang dùng. Khi thiếu WiX, `jpackage` có thể báo lỗi về toolchain; đó không phải bằng chứng `--win-per-user-install` không được hỗ trợ. Có thể chạy `jpackage --help` để kiểm tra flag nền tảng và `jpackage --version` để xác định bản công cụ. Nên dùng CI/VM Windows có WiX phù hợp và quyền thử nghiệm installer.

### 4.3. Phần đã kiểm chứng end-to-end

Trong Windows JDK 24, một project tạm tương đương đã được biên dịch bằng `javac`, tạo JAR bằng `jar`, chạy `java -jar`, tạo `jpackage --type app-image` và chạy launcher Windows. Kết quả chính xác:

```text
--- java -jar ---
application=ScopeDemoApp
args=0
launcherExists=True
--- app image launcher ---
application=ScopeDemoApp
args=0
jpackageTypeHelpHasPerUser=True
```

Hai dòng `application` và `args` là **stdout của chương trình Java**; các dòng `launcherExists` và `jpackageTypeHelpHasPerUser` là **kết quả kiểm tra bằng PowerShell**. Điều này xác nhận JAR/launcher hoạt động và bản `jpackage` đang dùng có option, **không chứng minh MSI đã build hoặc cài thành công**.

Sau khi build được MSI trên máy có WiX, phần cần kiểm tra tiếp là đúng **file `.msi`/`.exe`**, **scope**, thư mục cài và sự hiện diện của ứng dụng trong danh sách đã cài đặt.

## 5. Quy trình kiểm thử phạm vi thực tế trên Windows

**Không nên quyết định QA chỉ dựa vào việc lệnh `jpackage` trả mã 0.** Mỗi biến thể installer phải được thử cài/gỡ trong môi trường sạch.

### Per-user: thử với tài khoản tiêu chuẩn

1. Dùng **Windows VM/snapshot sạch**, tài khoản thường không thuộc Administrators nếu môi trường cho phép.
2. Chạy installer được build với `--win-per-user-install`.
3. Xác nhận thư mục cài nằm dưới profile tương ứng, ví dụ `%LOCALAPPDATA%\ScopeDemoApp` khi không tùy chỉnh `--install-dir`.
4. Chạy launcher, kiểm tra chức năng, shortcut và tài nguyên đi kèm.
5. Đăng nhập **tài khoản Windows khác**: không giả định ứng dụng đã được đăng ký/cài sẵn cho tài khoản đó.
6. Gỡ ứng dụng qua cơ chế hệ điều hành phù hợp, kiểm tra trạng thái shortcuts và file còn sót.
7. Thử cài phiên bản kế tiếp **cùng scope** và xác minh hành vi nâng cấp.

### Per-machine: thử với quản trị và người dùng thường

1. Khôi phục snapshot hoặc dùng một VM sạch **khác**.
2. Chạy installer không có `--win-per-user-install`.
3. Theo dõi thông báo nâng quyền/UAC và yêu cầu policy.
4. Xác nhận thư mục mặc định ở `%ProgramFiles%\ScopeDemoApp` (hoặc đường dẫn được cấu hình).
5. Với tài khoản tiêu chuẩn, thử chạy launcher đã cài và các tác vụ **được phép**, không cần cố ghi vào thư mục cài.
6. Kiểm tra hành vi Start Menu/Desktop, gỡ cài, nâng cấp và file/data được chia sẻ theo thiết kế.
7. Kiểm thử tương tác với antivirus, Windows policies và application data do nhiều tài khoản sử dụng.

### Đường dẫn kiểm tra nhanh bằng PowerShell

```powershell
# Đường dẫn được OS công bố cho tài khoản/máy thử:
$env:LOCALAPPDATA
$env:ProgramFiles

# Ví dụ nếu ứng dụng dùng các mặc định trên:
Test-Path "$env:LOCALAPPDATA\ScopeDemoApp"
Test-Path "$env:ProgramFiles\ScopeDemoApp"
```

Những dòng `Test-Path` **không phải quy tắc tuyệt đối** để chứng minh scope trong mọi installer vì `--install-dir` hoặc lựa chọn UI có thể thay đổi đường dẫn. Kết hợp **metadata package**, hành vi cài thực tế, shortcut, trạng thái uninstall và kiểm tra từ tài khoản khác. Không dùng `HKLM/HKCU` làm một phán đoán duy nhất nếu chưa xác minh hành vi của đúng installer/JDK.

**Không triển khai installer lên máy người dùng thật chỉ để thử.** Dùng máy thử/VM và snapshot để tránh ghi đè phần mềm đã dùng, gây xung đột upgrade hoặc cần quyền quản trị không cần thiết.

## 6. Khi cần đổi từ per-user sang per-machine (hoặc ngược lại)

**Không giả định đổi một flag và tăng version là tự chuyển dữ liệu an toàn.** Chuyển scope là một **thay đổi chiến lược cài đặt**:

- **Danh tính/upgrade của installer:** trên Windows, tên, version và mã định danh upgrade có thể ảnh hưởng đến cách Windows Installer nhận diện bản đang cài. `jpackage` có `--win-upgrade-uuid` cho chiến lược upgrade; đừng đổi tùy tiện hoặc dùng cùng một identity cho hai biến thể mà không kiểm thử.
- **Dữ liệu ứng dụng:** cài trong `Program Files` hay `AppData\Local` không nói lên nơi lưu **cấu hình và dữ liệu người dùng**. Ứng dụng nên tách dữ liệu ghi được khỏi thư mục code/runtime, dùng thư mục dữ liệu phù hợp với scope.
- **Nhiều tài khoản:** nếu chuyển từ mỗi-user sang một cài đặt toàn máy, từng profile có thể có settings riêng, cache hoặc phiên bản cũ. Một máy có thể đang có **nhiều cài đặt per-user**.
- **Shortcut và uninstall:** chuyển phạm vi có thể để lại shortcut hoặc mục gỡ cài của scope cũ nếu không có kế hoạch migration.
- **Chính sách doanh nghiệp:** cài toàn máy thường tương tác với công cụ deployment/IT; cài per-user có thể bị chặn bởi chính sách cho phép executable chạy từ AppData.

Quy trình an toàn: lập danh sách profile/cài đặt cũ → xác định identity và phương án gỡ → backup/migrate dữ liệu phù hợp → kiểm thử upgrade/uninstall trên VM → triển khai có kiểm soát. Không đề xuất chỉnh registry thủ công hoặc xóa dữ liệu profile chỉ để “sửa” scope.

## 7. Hệ điều hành khác Windows: không áp dụng cờ `--win-per-user-install`

Theo tài liệu `jpackage` hiện hành, `--win-per-user-install` là **tùy chọn Windows**, không phải flag dùng chung cho `pkg`/`dmg` macOS hoặc `deb`/`rpm` Linux.

| Nền tảng | Package types thường gặp | Điều cần hiểu về phạm vi |
|---|---|---|
| **Windows** | `msi`/`exe` | Có flag `--win-per-user-install`; vắng flag mặc định cài toàn máy |
| **Linux** | `deb`/`rpm` | Gói native thường do package manager ở cấp hệ thống quản lý, mặc định Oracle `jpackage` là `/opt/<app-name>`; không có `--linux-per-user-install` tương đương |
| **macOS** | `pkg`/`dmg` | `jpackage` không công bố `--mac-per-user-install` đối xứng; vị trí mặc định Oracle là `/Applications/<app-name>`, luồng install/copy và quyền còn phụ thuộc định dạng và cơ chế hệ điều hành |

**Giải pháp thay thế khi muốn triển khai theo người dùng trên Linux/macOS:** cân nhắc phân phối **`--type app-image`** (trên macOS là bundle `.app`, Linux là thư mục ứng dụng) để người dùng đặt ở vị trí của riêng họ **khi chính sách OS cho phép**. Đây là phân phối/chép bundle, **không phải** cùng tính năng cài per-user có quản lý của MSI.

Với macOS, người dùng có thể chọn chép ứng dụng `.app` từ DMG vào thư mục `Applications` phù hợp nếu có quyền; việc dùng `pkg` có các quy tắc quyền/đích và ký gói riêng. Không mặc định một flag Windows sẽ điều khiển macOS installer.

Với Linux, DEB/RPM liên quan quản lý hệ thống và quyền package manager; đừng đổi đường dẫn sang thư mục home rồi khẳng định đã tạo “per-user .deb/.rpm” tương đương. Nếu cần deployment cá nhân thật sự, hãy chọn công nghệ phân phối phù hợp hoặc app image cùng quy trình quản lý riêng.

**Lưu ý cross-platform:** `jpackage` không hỗ trợ build installer Windows từ macOS/Linux hay ngược lại theo cách trực tiếp. Build đúng OS/architecture và kiểm tra `jpackage --help` của máy build để biết các tùy chọn platform-specific hiện diện.

## 8. Những lỗi thường gặp

| Sai lầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Quên cờ `--win-per-user-install` nhưng tưởng tạo installer user | Mặc định Windows là **per-machine** | Ghi rõ cờ trong cấu hình build cho user scope |
| Dùng `--win-per-user-install` với `--type app-image` rồi coi đó là installer | App image không tạo quy trình install | Chọn `--type msi`/`exe` khi thật sự cần native installer |
| Dùng `--install-dir` hoặc `--win-dir-chooser` để đổi scope | Chúng chỉ điều chỉnh đường dẫn/đối thoại cài | Dùng đúng cờ scope và QA quyền |
| Cho rằng per-user tuyệt đối không cần nâng quyền | Môi trường/doanh nghiệp/tác vụ hệ thống có chính sách riêng | Thử bằng tài khoản chuẩn trên Windows sạch |
| Cho rằng per-machine tự làm mọi profile có dữ liệu giống nhau | Code/runtime chung không đồng nghĩa settings/data chung | Thiết kế app data rõ theo user hay machine |
| Một máy có cả user/machine installer cùng tên/version gây xung đột | Danh tính gói và chiến lược upgrade chưa được kiểm thử | Thử riêng trên VM, hoạch định migration và uninstall |
| Gõ cờ Windows trong job Linux/macOS | Flag platform-specific không tồn tại | Dùng OS-specific package flow |
| Đã build thành công nhưng launcher lỗi | Thiếu Java module, JAR, resources hoặc native libraries | Chạy smoke test sau cài |
| MSI không build dù cú pháp đúng | Thiếu WiX toolchain tương thích hoặc quyền build | Kiểm tra `jpackage --help`, WiX/JDK version và log |
| Cài được vào `Program Files` rồi app ghi file trực tiếp ở đó bị lỗi | Thư mục code thường không cho user thường ghi | Lưu dữ liệu runtime trong thư mục dữ liệu hợp lệ thay vì ghi cạnh launcher |
| Giữ mật khẩu/token trong `--arguments` hoặc file staging | Cấu hình installer/payload có thể bị trích xuất | Dùng cơ chế quản lý secret đúng môi trường |
| Chọn scope khác nhau mà không thay quy trình release | Shortcut, uninstall, deployment, upgrade có thể khác | Kiểm thử từng biến thể trước khi phân phối |

## 9. Checklist QA và release

1. Dùng **JDK 17+** và kiểm tra `jpackage --version`, `jpackage --help` trên Windows build host.
2. Build JAR/module, kiểm tra main class, resources và dependencies trước khi đóng gói.
3. Chọn **native installer** `--type msi` hoặc `--type exe`; không nhầm với `--type app-image`.
4. **Chọn scope từ lúc build:** có `--win-per-user-install` khi muốn per-user, không có khi muốn per-machine.
5. Nếu chỉ đổi đường dẫn/shortcut, dùng `--install-dir`, `--win-dir-chooser`, `--win-shortcut`, `--win-menu` đúng mục tiêu; **không** dựa vào chúng để thay scope.
6. Ghi rõ version, name, upgrade strategy; không phát hành hai biến thể cùng identity mà chưa thử tương tác.
7. Tạo installer trên máy **Windows có WiX** tương thích với JDK, không cross-build từ OS khác.
8. **QA trên VM sạch:** tài khoản thường cho per-user, quyền admin và user thường cho per-machine, kiểm tra UAC và chính sách.
9. Kiểm tra nơi cài, launcher, Java runtime, Start Menu/Desktop, file dữ liệu và quyền ghi.
10. Kiểm tra uninstall, upgrade và trường hợp có bản cài cùng app ở scope khác.
11. Nếu triển khai Linux/macOS, dùng đúng installer/app-image riêng; không đưa flag Windows vào script.
12. Giữ secrets ra khỏi JAR/package và đánh giá code signing, ký gói, bảo mật dữ liệu.
13. Chỉ kết luận installer “đã được thử thành công” sau khi **cài, chạy, gỡ và nâng cấp** trong môi trường mục tiêu; xác nhận cú pháp hoặc chạy app image chưa đủ.

## Tài liệu tham khảo chính thức

- Oracle Java SE 25, `The jpackage Command` — nhóm tùy chọn Windows `--win-per-user-install`, `--win-dir-chooser`, `--install-dir`, `--win-shortcut`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html
- Oracle Java SE 25, `Basic Packaging` — thư mục cài mặc định Windows Program Files / AppData Local, Linux `/opt` và macOS `/Applications`: https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html
- Oracle Java SE 25, `Manage the Installation of Your Application` — `--install-dir`, `--win-dir-chooser` và shortcuts: https://docs.oracle.com/en/java/javase/25/jpackage/manage-installation.html
- Oracle Java SE 17, `The jpackage Command` — xác nhận cú pháp ổn định trong bản JDK LTS: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html
- OpenJDK JEP 392, `Packaging Tool` — `jpackage` chính thức từ JDK 16: https://openjdk.org/jeps/392
