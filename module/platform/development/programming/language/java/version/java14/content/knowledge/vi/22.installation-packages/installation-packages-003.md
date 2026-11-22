# Thư mục cài đặt, shortcut và tích hợp hệ điều hành khi dùng jpackage

## Mục tiêu

`jpackage` đóng gói ứng dụng Java và Java runtime thành **application image** hoặc **gói cài đặt native**. Khi phát hành một ứng dụng, ngoài việc launcher khởi chạy được, bạn cần hiểu **vị trí cài đặt**, **quyền cài**, **shortcut/menu**, **icon**, **liên kết loại tệp (file association)** và cách hệ điều hành quản lý nâng cấp/gỡ cài.

Sau bài này, bạn sẽ:

- Phân biệt `--input`, `--dest`, `--install-dir` và tệp do installer thực sự ghi vào máy người dùng.
- Chọn đúng các options Windows: `--win-menu`, `--win-shortcut`, `--win-menu-group`, `--win-shortcut-prompt`, `--win-dir-chooser`, `--win-per-user-install`.
- Hiểu menu/desktop entries Linux và `--linux-shortcut`/`--linux-menu-group`, cũng như mô hình `.app` bundle của macOS.
- Cấu hình icon cho đúng OS; tạo file association bằng `--file-associations` để mở một định dạng file riêng.
- Biết vì sao `app-image` chưa tương đương việc đã **cài** ứng dụng và tạo shortcut.
- Xây ví dụ Java 17+, tạo JAR, dùng `jpackage` tạo image trên Windows, rồi **kiểm tra launcher có nhận argument**.
- Tách program files khỏi dữ liệu người dùng; thiết kế kiểm thử cài, nâng cấp, uninstall và các yêu cầu bảo mật.

**Phiên bản:** `jpackage` được giới thiệu dạng incubator ở Java 14 (JEP 343) và chuẩn hóa thành công cụ chính thức ở **Java 16** ([JEP 392](https://openjdk.org/jeps/392)). Bài dùng cú pháp **JDK 17 trở lên** và các tùy chọn trong tài liệu Oracle JDK 25, không dùng incubator APIs hay flags preview không còn áp dụng. Các lệnh theo từng hệ điều hành chỉ chạy trên nền tảng tương ứng.

## 1. Phân biệt input, output và nơi cài đặt

Giả sử bạn đã biên dịch ứng dụng thành `DeskNotes.jar`:

~~~text
project/
    DeskNotes.java
    input/
        DeskNotes.jar
    dist/
        ... artifact jpackage sẽ tạo ...
~~~

| Option | Chức năng | Ví dụ |
|---|---|---|
| `--input` | Thư mục chứa các **tệp ứng dụng cần đưa vào gói** | `--input input` |
| `--main-jar` | JAR chính, đường dẫn **tương đối bên trong `--input`** | `--main-jar DeskNotes.jar` |
| `--dest` | Nơi ghi **kết quả build** (installer hoặc app-image) | `--dest dist` |
| `--install-dir` | **Vị trí cài** trên máy người dùng khi chạy native installer | `--install-dir DeskNotes` trên Windows |
| `--temp` | Thư mục tạm trong quá trình đóng gói | Không phải user data directory |
| `--resource-dir` | Thư mục template/icon/resources tùy chỉnh build | Dùng khi cần override packaging templates |

`--dest dist` không có nghĩa ứng dụng sẽ được cài vào thư mục `dist` của người dùng. Nó là **thư mục output của máy build**. `--install-dir` là tùy chọn **bên trong gói cài đặt**, và cách diễn giải khác nhau theo OS.

**Bảo mật đầu vào:** `jpackage` có thể đưa tất cả các file trong `--input` vào application image. Không đưa secrets, khóa ký, build cache, file test nhạy cảm hay cấu hình chứa mật khẩu vào đây.

### App-image không phải native installer

~~~bash
# Tạo application image, chưa cài lên hệ điều hành:
jpackage --type app-image --name DeskNotes --input input --main-jar DeskNotes.jar --dest dist
~~~

Image chứa launcher, các tệp app và Java runtime. Bạn có thể **mở executable trực tiếp từ image**, nhưng việc tạo image **không tự đăng ký ứng dụng vào Start Menu, Desktop, file associations hoặc package manager**.

Trên Windows, lệnh tạo installer có dạng:

~~~powershell
jpackage --type exe --name DeskNotes --input input --main-jar DeskNotes.jar --dest dist
~~~

Hai lệnh là hai mục đích khác nhau. `--type exe` chỉ chạy trên Windows và cần toolchain phù hợp, thường là WiX. Linux dùng `deb`/`rpm`; macOS dùng `dmg`/`pkg`. `jpackage` **không tạo native installer cho OS khác** từ cùng một máy build.

**Quy tắc QA:** Chạy launcher của `app-image` để kiểm tra startup; sau đó phải **cài** native package trên máy/VM đích mới được kết luận shortcut/menu/file association đã hoạt động.

## 2. Thư mục cài đặt theo từng OS

Theo tài liệu Oracle Packaging Tool, các mặc định điển hình:

| Hệ điều hành | Đường dẫn cài mặc định | Ý nghĩa |
|---|---|---|
| Windows per-machine | `C:\Program Files\DeskNotes` | Cài chung theo máy, có thể yêu cầu quyền cao |
| Windows per-user | `C:\Users\username\AppData\Local\DeskNotes` | Cài theo tài khoản với `--win-per-user-install` |
| Linux | `/opt/DeskNotes` | Thường thuộc vùng do package manager/admin kiểm soát |
| macOS | `/Applications/DeskNotes`, với application bundle `.app` | Phân phối theo conventions của macOS |

`username` trong bảng là phần minh họa của đường dẫn, không phải một tài khoản thật. Vị trí thực tế có thể thay đổi do lựa chọn của người cài, chính sách công ty hoặc cách triển khai.

### 2.1. --install-dir: Windows khác Linux/macOS

Theo `jpackage` manual hiện hành:

- **Windows:** `--install-dir` nhận **đường dẫn con tương đối** trong vùng cài đặt do OS/mode quyết định; ví dụ `DeskNotes` hoặc `Vendor\DeskNotes`. **Không** dùng một đường dẫn tuyệt đối kiểu `C:\...` như trên Linux.
- **Linux/macOS:** `--install-dir` nhận **đường dẫn tuyệt đối**, ví dụ `/opt/desknotes` hoặc `/Applications/DeskNotes`.

Windows PowerShell:

~~~powershell
jpackage --type exe --name DeskNotes --input input --main-jar DeskNotes.jar --install-dir DeskNotes --dest dist
~~~

Linux Bash:

~~~bash
jpackage --type deb --name DeskNotes --input input --main-jar DeskNotes.jar --install-dir /opt/desknotes --dest dist
~~~

macOS Bash:

~~~bash
jpackage --type pkg --name DeskNotes --input input --main-jar DeskNotes.jar --install-dir /Applications/DeskNotes --dest dist
~~~

**Không chạy lệnh dành cho Linux/macOS trên Windows và ngược lại.** Loại package, vị trí cài và bộ công cụ native là platform-specific.

### 2.2. Thư mục cài không phải nơi ghi dữ liệu người dùng

Đừng tạo file database/log/tài liệu của mỗi user ngay cạnh launcher. Trong nhiều môi trường:

- `Program Files` trên Windows bị hạn chế quyền ghi.
- `/opt` trên Linux thường do root/package manager quản lý.
- `/Applications` và nội dung `.app` trên macOS thuộc phần chương trình được cài, có thể bị thay khi nâng cấp.

Hãy lưu **program binaries/runtime** trong thư mục cài, còn **user data** ở thư mục phù hợp OS/account: Windows AppData, Linux theo XDG conventions, macOS Application Support. Ứng dụng phải xử lý quyền, backup và migration; `jpackage` không tự quản lý dữ liệu nghiệp vụ.

## 3. Windows: Start Menu, Desktop shortcut và phạm vi cài

| Option | Chức năng | Phân biệt |
|---|---|---|
| `--win-menu` | Yêu cầu thêm **Start Menu shortcut** | Không tự đồng nghĩa Desktop shortcut |
| `--win-menu-group` | Nhóm ứng dụng trong Start Menu | Có ý nghĩa khi đi với `--win-menu` |
| `--win-shortcut` | Yêu cầu thêm **Desktop shortcut** | Khác Start Menu entry |
| `--win-shortcut-prompt` | Hội thoại cho phép user quyết định shortcuts được yêu cầu | Cần có `--win-menu` và/hoặc `--win-shortcut` |
| `--win-dir-chooser` | Hội thoại chọn **thư mục cài** | Khác per-user install |
| `--win-per-user-install` | Cài theo tài khoản hiện tại thay vì per-machine | Vị trí và quyền thay đổi |
| `--win-console` | Tạo console launcher trên Windows | Dùng cho CLI hoặc app cần console |
| `--win-upgrade-uuid` | Identity phục vụ nâng cấp Windows installer | Giữ ổn định trong cùng một sản phẩm |
| `--app-version` | Version của ứng dụng/gói | Cần quản lý chu trình phát hành |

### 3.1. Ví dụ: installer Windows tạo Start Menu và Desktop shortcut

Lệnh **PowerShell một dòng**:

~~~powershell
jpackage --type exe --name DeskNotes --app-version 1.0.0 --input input --main-jar DeskNotes.jar --dest dist --install-dir DeskNotes --win-menu --win-menu-group "Desk Tools" --win-shortcut --win-shortcut-prompt --win-dir-chooser
~~~

Phân tích:

1. `--type exe` yêu cầu native EXE installer.
2. `--win-menu` yêu cầu Start Menu entry; `--win-menu-group "Desk Tools"` đặt tên nhóm.
3. `--win-shortcut` yêu cầu Desktop shortcut, không thay cho `--win-menu`.
4. `--win-shortcut-prompt` thêm lựa chọn shortcut trong quy trình cài đặt.
5. `--win-dir-chooser` cho người dùng chọn vị trí cài khi installer hỗ trợ UI.
6. `--install-dir DeskNotes` xác định subpath cài Windows theo quy tắc của công cụ.

**Đây là mẫu lệnh theo tài liệu, không phải installer đã được kiểm thử cài đặt.** Máy Windows dùng để chạy ví dụ Java trong bài không có WiX; vì vậy không có bằng chứng thử nghiệm native `exe`/`msi`, Start Menu hay desktop shortcut. Phần được biên dịch và chạy thực tế là `app-image` ở mục 7.

### 3.2. Start Menu, Desktop và Launcher là ba thứ khác nhau

- **Launcher:** executable thật của ứng dụng, ví dụ `DeskNotes.exe` trong thư mục cài.
- **Start Menu entry:** shortcut trong menu ứng dụng Windows; yêu cầu qua `--win-menu`.
- **Desktop shortcut:** lối tắt trên desktop; yêu cầu qua `--win-shortcut`.

Một ứng dụng có thể khởi chạy từ thư mục cài mà không có shortcut, hoặc có Start Menu nhưng không có Desktop shortcut. Không đánh giá sai tình trạng package chỉ vì quan sát một loại entry.

### 3.3. Per-user install và quyền

Ví dụ cài theo tài khoản:

~~~powershell
jpackage --type exe --name DeskNotes --input input --main-jar DeskNotes.jar --dest dist --win-per-user-install --win-menu --win-shortcut
~~~

Cài per-user thường dùng vùng `AppData\Local` thay vì `Program Files`. Điều này không cho phép vượt chính sách bảo mật hoặc bỏ qua giới hạn OS. `--win-dir-chooser` **chỉ quản lý hộp thoại chọn đường dẫn**, không thay thế `--win-per-user-install`.

### 3.4. Nâng cấp, gỡ cài

`--win-upgrade-uuid` là một thành phần nhận diện chuỗi nâng cấp; nếu ứng dụng được nâng cấp như cùng một sản phẩm, hãy **giữ identity ổn định** thay vì tạo UUID mới mỗi release. `--app-version` biểu diễn version ứng dụng/gói, không thay thế kiểm thử upgrade.

Khi phát hành, thử lần lượt **cài v1 → mở v1 → nâng cấp v2 → mở v2 → uninstall**. Xác minh lối tắt không trỏ tới launcher cũ, file associations đúng chính sách, user data được giữ hoặc xóa theo thiết kế.

## 4. Linux: desktop entry và menu group

Gói Linux thường là `deb` hoặc `rpm`. Tích hợp giao diện desktop dùng `.desktop` entries và icon, nhưng cách hiển thị còn phụ thuộc **desktop environment**. Một Linux server không có GUI sẽ không tự có desktop/menu ứng dụng.

| Option | Chức năng |
|---|---|
| `--linux-shortcut` | Yêu cầu tạo launcher/shortcut cho ứng dụng Linux GUI |
| `--linux-menu-group` | Nhóm trong menu ứng dụng |
| `--linux-package-name` | Tên package Linux, có thể khác tên app |
| `--linux-app-category` | Category/section metadata của package |
| `--linux-package-deps` | Dependencies/capabilities cần thiết cho package |
| `--icon` | Icon launcher, thường `.png` trên Linux |
| `--install-dir` | Đường dẫn cài tuyệt đối trên Linux |

Lệnh minh họa **Linux có công cụ đóng DEB**:

~~~bash
jpackage --type deb --name DeskNotes --linux-package-name desknotes --input input --main-jar DeskNotes.jar --install-dir /opt/desknotes --linux-shortcut --linux-menu-group Office --dest dist
~~~

Oracle lưu ý **custom icon trên Linux** cũng có thể khiến shortcut được tạo ngay cả khi không thêm `--linux-shortcut`. Nhưng shortcut có hiện ở **desktop**, **app launcher** hay menu cụ thể còn do distro, desktop environment và policy quyết định.

**Kiểm tra:** Build trên distro đích; kiểm tra package và file `.desktop` (đặc biệt `Exec`/`Icon`); cài trên VM/desktop test; mở app từ menu; gỡ bằng package manager và kiểm tra các entry được dọn. Đừng suy từ build trên headless Linux sang kết quả GUI.

## 5. macOS: .app bundle, Finder, Dock và menu bar

Trên macOS, ứng dụng thường được phân phối dưới dạng **`.app` bundle** trong `dmg` hoặc `pkg`. Finder/Dock/Launchpad và menu bar không giống Start Menu/Desktop shortcut của Windows.

| Option | Tác dụng |
|---|---|
| `--mac-package-name` | Tên hiển thị ứng dụng trong menu bar/Info; thường nên ngắn |
| `--mac-package-identifier` | Định danh app, thường có dạng reverse-domain |
| `--mac-app-category` | Category metadata của application bundle |
| `--icon` | Icon app, thường `.icns` trên macOS |
| `--mac-sign` | Yêu cầu ký code/gói khi có signing identity hợp lệ |
| `--install-dir` | Đường dẫn cài tuyệt đối, ví dụ `/Applications/DeskNotes` |

Ví dụ lệnh chỉ chạy trên macOS:

~~~bash
jpackage --type pkg --name DeskNotes --input input --main-jar DeskNotes.jar --mac-package-name DeskNotes --mac-package-identifier com.example.desknotes --install-dir /Applications/DeskNotes --dest dist
~~~

Có thể chọn `--type dmg` thay `pkg` cho một kiểu phân phối khác. Với DMG, người dùng có thể kéo `.app` vào Applications; PKG là installer theo cách của OS. `--mac-package-name` **không tạo Windows-like Desktop shortcut**, nó xác định một tên hiển thị trong hệ thống Mac.

Để phát hành cho máy ngoài môi trường phát triển, kiểm tra **code signing, notarization, Gatekeeper, entitlements** nếu được yêu cầu. Một `.app` chạy trên máy build chưa bảo đảm sẽ vượt các kiểm tra bảo mật khi người dùng tải về.

## 6. Icon, file associations và launcher bổ sung

### 6.1. Icon đúng dạng

| OS | Định dạng icon thường dùng | Bối cảnh |
|---|---|---|
| Windows | `.ico` | Executable, Start Menu, Desktop |
| Linux | `.png` | `.desktop`, app menu |
| macOS | `.icns` | `.app`, Finder/Dock |

`--icon path` được dùng để đưa icon ứng dụng vào package. Đừng dùng một file icon duy nhất mà chưa kiểm tra định dạng/kích thước của nền tảng. Icon của **loại file** có thể khác icon **ứng dụng**.

### 6.2. Liên kết đuôi .dnote với DeskNotes

Để yêu cầu hệ điều hành mở file `.dnote` bằng ứng dụng, tạo một file **`desknotes-association.properties`**:

~~~properties
extension=dnote
mime-type=application/x-desknotes
description=DeskNotes document
~~~

`extension` không có dấu chấm ở đầu. MIME type ở đây là **ví dụ do ứng dụng quy ước**, không khẳng định đây là MIME type đã đăng ký với tổ chức tiêu chuẩn.

Windows installer:

~~~powershell
jpackage --type exe --name DeskNotes --input input --main-jar DeskNotes.jar --file-associations desknotes-association.properties --win-menu --dest dist
~~~

Theo tài liệu JDK, `--file-associations` được phép sử dụng nhiều lần, mỗi lần chỉ một properties file mô tả một association; các khóa hỗ trợ gồm `extension`, `mime-type`, `icon` và `description`.

**Giới hạn:** association không ép OS phải đặt DeskNotes làm ứng dụng mặc định. Người dùng có thể chọn app khác; hệ thống có thể yêu cầu xác nhận theo policy. `jpackage` chỉ khai báo integration; chương trình Java vẫn phải **nhận đường dẫn, kiểm tra và mở file** một cách an toàn.

### 6.3. Launcher phụ

`--add-launcher name=propertiesFile` cho phép thêm executable khác trong cùng app image/package. Một file **`desknotes-cli.properties`** minh họa:

~~~properties
main-jar=DeskNotes.jar
main-class=DeskNotes
arguments=--help
win-console=true
~~~

Lệnh Windows:

~~~powershell
jpackage --type exe --name DeskNotes --input input --main-jar DeskNotes.jar --add-launcher DeskNotesCLI=desknotes-cli.properties --dest dist
~~~

Đây là **minh họa cấu hình**, không phải launcher thứ hai đã được chạy thử. Source `DeskNotes` tại mục 7 chỉ in argument và chưa triển khai chức năng help. Tùy từng OS, properties file có thể khai báo thêm `win-shortcut`, `win-menu` hoặc `linux-shortcut` cho launcher phụ.

**Không nhầm `--launcher-as-service` với shortcut.** Service là tiến trình nền được tích hợp với cơ chế lifecycle của OS, cần quản lý quyền tài khoản, start/stop, logging và uninstall riêng. Một GUI app không nên bật service chỉ để có icon trên desktop.

## 7. Ví dụ Java 17 chạy được: JAR, app-image và đường dẫn tệp

Tệp **`DeskNotes.java`**:

~~~java
import java.nio.file.Path;

public final class DeskNotes {
    public static void main(String[] args) {
        System.out.println("app=DeskNotes");
        System.out.println("argCount=" + args.length);

        if (args.length > 0) {
            Path path = Path.of(args[0]);
            System.out.println("requestedFile=" + path.getFileName());
        }
    }
}
~~~

Ví dụ chỉ **in tên file** nếu launcher nhận được argument. Nó **không đọc nội dung file** và không tự đăng ký file association. Trong chương trình thật, `Path.of` có thể ném ngoại lệ nếu input không hợp lệ; cần kiểm tra file size, permissions, loại dữ liệu và nội dung không tin cậy trước khi parse.

### 7.1. Build JAR và chạy

Lệnh Bash:

~~~bash
mkdir -p classes input images
javac --release 17 -encoding UTF-8 -d classes DeskNotes.java
jar --create --file input/DeskNotes.jar --main-class DeskNotes -C classes .
java -jar input/DeskNotes.jar
java -jar input/DeskNotes.jar sample.dnote
~~~

**Đầu ra đã được kiểm chứng, không có đối số:**

~~~text
app=DeskNotes
argCount=0
~~~

**Đầu ra đã được kiểm chứng, có đối số:**

~~~text
app=DeskNotes
argCount=1
requestedFile=sample.dnote
~~~

### 7.2. Tạo và kiểm chứng app-image trên Windows

Trên Windows PowerShell sau khi có `input/DeskNotes.jar`, chạy:

~~~powershell
jpackage --type app-image --name DeskNotes --input input --main-jar DeskNotes.jar --dest images --win-console
~~~

Sau đó thử launcher:

~~~powershell
& "./images/DeskNotes/DeskNotes.exe"
& "./images/DeskNotes/DeskNotes.exe" "sample.dnote"
~~~

**Kết quả thực tế:** Hai lần chạy launcher trong app-image cho stdout **khớp hoàn toàn hai lần `java -jar` ở trên**. Mã được biên dịch bằng `javac --release 17` và image được tạo bằng **JDK 24.0.2 trên Windows**.

**Giới hạn kiểm chứng:** Máy thử **không cài WiX**. Vì vậy bài chỉ tuyên bố đã tạo và chạy **app-image**, **không tuyên bố đã tạo/cài native EXE hoặc MSI**, không khẳng định đã xác minh Start Menu, Desktop shortcut, file associations hay uninstall. Các lệnh installer trước đó là **mẫu từ tài liệu Oracle**, phải thử lại khi có đầy đủ OS và toolchain.

## 8. Kiểm tra tích hợp sau khi cài thực tế

### Quy trình dành cho QA/release

1. **Build:** JAR chính/dependencies/resources đầy đủ, không chứa secrets trong `--input`.
2. **App-image:** xây `--type app-image`, mở launcher đã đóng gói và thử argument/resources.
3. **Installer:** dùng native package của đúng OS, trên máy/VM có toolchain tương thích.
4. **Installation directory:** kiểm tra path cài, quyền user, khả năng chọn thư mục khi bật chooser.
5. **Windows:** kiểm tra launcher, Start Menu, Desktop shortcut **riêng biệt**; thử per-user/per-machine.
6. **Linux:** kiểm tra `.desktop`, category/menu, icon và `Exec` trên desktop environment thực.
7. **macOS:** kiểm tra `.app`, Finder/Dock, menu bar, ký/notarize/Gatekeeper.
8. **File associations:** double-click file mẫu, xác nhận đúng app nhận argument và mở file an toàn.
9. **Upgrade:** cài v1, nâng v2, kiểm tra shortcut/association cũ, giữ dữ liệu đúng policy.
10. **Uninstall:** gỡ qua OS package manager/installer, kiểm tra entry còn sót và dữ liệu nên giữ.
11. **Bảo mật:** dữ liệu user ở data directory, không ghi vào `Program Files`/`/Applications`/`/opt` tùy tiện.
12. **Bằng chứng:** chụp/log đường dẫn cài, tên launcher, version, OS, hành vi sau cài; đừng chỉ nhìn `jpackage` exit code.

### Bảng lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| `--dest` được coi là nơi cài app | Phân biệt sai build path và install path | `--dest` cho output, `--install-dir` cho máy user |
| App-image có launcher nhưng thiếu Start Menu | Chưa cài native installer | Dùng `--type exe/msi` và test cài |
| Chỉ có `--win-shortcut` mà đòi menu entry | Desktop khác Start Menu | Thêm `--win-menu` |
| Chỉ có `--win-menu-group` | Group không tự tạo menu shortcut | Cần `--win-menu` |
| Tưởng `--win-dir-chooser` là per-user install | Hai tùy chọn khác chức năng | Dùng `--win-per-user-install` nếu cần |
| `--install-dir` Windows dùng path tuyệt đối tùy ý | Không đúng hợp đồng relative subpath | Dùng subpath hoặc chooser |
| `--install-dir` Linux/macOS dùng path tương đối | Sai yêu cầu đường dẫn tuyệt đối | Cung cấp `/opt/...` hoặc `/Applications/...` |
| Linux headless không hiện icon | Không có desktop environment | Kiểm tra trên GUI đích |
| `--mac-package-name` được coi là desktop shortcut | Mac dùng bundle/menu khác Windows | Dùng conventions của macOS |
| Icon không hiển thị | Sai format, shortcut chưa tạo, cache | Kiểm tra `.ico`, `.png`, `.icns` và OS |
| File association mở app nhưng không mở file | Chưa viết logic đọc file argument | Validate `args[0]`, xử lý path và dữ liệu |
| Mọi association sẽ tự thành mặc định | OS và user quyết định default app | Test/tôn trọng user choice |
| Ghi log vào thư mục cài | Lỗi quyền hoặc bị ghi đè khi update | Sử dụng user data dir |
| UUID nâng cấp thay đổi mỗi build | Upgrade identity có thể bị đứt | Giữ identity ổn định cho sản phẩm |
| Chỉ test launcher trước khi đóng gói | Phụ thuộc/runtime có thể thiếu sau build | Test image launcher và installer |
| Tuyên bố installer PASS khi chỉ tạo `.exe` | Chưa test OS integration/uninstall | Cài trong VM/máy test sạch |

## 9. Bài tự kiểm tra

**Câu 1.** `--input input --dest dist --install-dir DeskNotes` có phải ba cách viết cùng một thư mục không?

**Đáp án:** Không. `--input` là nguồn tệp đóng gói; `--dest` là nơi tạo artifact; `--install-dir` là nơi ứng dụng sẽ được cài khi chạy native installer.

**Câu 2.** Tạo `--type app-image` thành công nhưng không có Windows Desktop shortcut. Có đủ chứng minh công cụ lỗi không?

**Đáp án:** Chưa. App-image không tự cài và đăng ký shortcut. Cần build/cài native installer và yêu cầu `--win-shortcut`.

**Câu 3.** Muốn cả Start Menu và Desktop trên Windows?

**Đáp án:** Dùng `--win-menu` và `--win-shortcut`; thêm `--win-menu-group`/`--win-shortcut-prompt` khi cần.

**Câu 4.** Hai option `--win-dir-chooser` và `--win-per-user-install` có đồng nghĩa không?

**Đáp án:** Không. Một option thêm UI chọn đường dẫn; option còn lại quy định phạm vi cài theo tài khoản.

**Câu 5.** Linux app có `--linux-shortcut` nhưng chạy trên Linux server không GUI mà không có icon, chắc chắn sai?

**Đáp án:** Không. Desktop shortcut/menu phụ thuộc môi trường GUI cụ thể.

**Câu 6.** macOS `--mac-package-name` có tạo Windows-style desktop shortcut?

**Đáp án:** Không. Nó điều chỉnh tên hiển thị trong môi trường macOS; app được quản lý theo bundle/Launch Services.

**Câu 7.** Double-click một file `.dnote` đã gán association, ứng dụng mở ra nhưng không đọc nội dung. Thiếu gì?

**Đáp án:** Thiếu logic nhận và xử lý file path của chương trình. Association không tự parse file.

**Câu 8.** Vì sao không lưu database/log user trong thư mục cài?

**Đáp án:** Có thể thiếu quyền, bị thay thế khi upgrade/uninstall và lẫn dữ liệu nhiều tài khoản. Tách data khỏi app binaries.

## Tài liệu chính thức

- [Oracle JDK 25 — Manage Installation](https://docs.oracle.com/en/java/javase/25/jpackage/manage-installation.html): thư mục cài, shortcut, Start Menu, icon và điều khiển UI.
- [Oracle JDK 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): các đường dẫn mặc định theo OS.
- [Oracle JDK 25 — jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): options đầy đủ cho Windows/Linux/macOS, `--install-dir`, `--file-associations`, `--add-launcher`.
- [Oracle JDK 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): image, native installers, yêu cầu OS/toolchain.
- [Oracle JDK 21 — Support Application Requirements](https://docs.oracle.com/en/java/javase/21/jpackage/support-application-features.html): file-association properties và extension/MIME.
- [Oracle JDK 25 — Override Resources](https://docs.oracle.com/en/java/javase/25/jpackage/override-jpackage-resources.html): icon và Linux `.desktop` templates.
- [Oracle JDK 17 — jpackage Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): cú pháp từ Java 17.
- [OpenJDK — JEP 392: Packaging Tool](https://openjdk.org/jeps/392): mốc chuẩn hóa Java 16.

**Ghi nhớ:** `--input` là thư mục **nguồn payload**, `--dest` là nơi ghi **file gói trên máy build**, còn `--install-dir` là **thư mục cài trên máy người dùng**. Shortcut/Start Menu, Linux desktop entry, macOS app bundle và file association đều phụ thuộc hệ điều hành. **Không lấy việc tạo app-image làm bằng chứng đã cài và tích hợp OS thành công**: luôn kiểm tra một native installer trên chính nền tảng đích.