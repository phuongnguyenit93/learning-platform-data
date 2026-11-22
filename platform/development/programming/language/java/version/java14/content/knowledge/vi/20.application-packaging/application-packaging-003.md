# Phân biệt app image với gói cài đặt native bằng jpackage

## 1. Hai loại đầu ra phục vụ hai nhu cầu khác nhau

Công cụ **`jpackage`** trong JDK giúp đóng gói ứng dụng Java để người dùng chạy bằng launcher của hệ điều hành thay vì phải tự tìm Java, dựng classpath và nhập `java -jar`. Công cụ có thể tạo **application image (app image)** hoặc **gói cài đặt native (native installer/package)**. Đây là hai loại artifact liên quan, nhưng không đồng nghĩa.

- **App image** (`--type app-image`) là **thư mục hoặc bundle ứng dụng có thể chạy trực tiếp** trên nền tảng được build. Nó chứa launcher, các JAR/module, resource và **Java runtime** được đóng gói. Tạo image **không tự chạy quy trình cài đặt**, không tự tạo entry gỡ cài đặt hệ thống hay đăng ký app vào package manager.
- **Native package/installer** (ví dụ `--type msi`, `exe`, `deb`, `rpm`, `pkg`, `dmg`) là **file phân phối theo định dạng hệ điều hành**. Hệ thống có thể cài/copy application image vào vị trí đích, tích hợp shortcut, menu, metadata phiên bản và cơ chế cài/gỡ theo loại package.

Đây không phải hai cách biên dịch Java thành hai ngôn ngữ máy khác nhau. **Cả hai thường chứa cùng Java app + Java runtime**; khác biệt chính nằm ở **artifact phân phối và vòng đời cài đặt**.

**Phiên bản áp dụng:** `jpackage` đã có ở JDK 14/15 dưới dạng incubating tool, nhưng được chính thức hóa thành công cụ production-ready từ **JDK 16** (JEP 392). Bài sử dụng cú pháp đã chuẩn hóa và được duy trì trong các tài liệu Java 17/25/26, không sử dụng hướng dẫn cũ liên quan đến module incubator `jdk.incubator.jpackage`.

## 2. Bảng so sánh nhanh

| Tiêu chí | App image | Native installer/package |
| --- | --- | --- |
| Tùy chọn `jpackage` | `--type app-image` | `--type msi/exe/deb/rpm/pkg/dmg` theo OS |
| Kết quả | **Thư mục/bundle** | **File cài đặt/phân phối** |
| Launcher native | Có | Có, nằm trong ứng dụng được cài/phân phối |
| Java runtime đi kèm | Có | Có, thông qua app image bên trong package |
| Chạy thử trực tiếp sau build | Chạy launcher trong thư mục/bundle | Thường mở/cài package rồi chạy bản đã cài |
| Tạo shortcut, menu/entry hệ thống | Không tự động khi chỉ tạo image | Có thể cấu hình tùy nền tảng/format |
| Trạng thái cài đặt/gỡ cài | Không tự tạo | Tùy loại package, có thể tích hợp với OS/package manager |
| Nâng cấp ứng dụng | Tự thiết kế quy trình thay image | Có thể dùng quy trình upgrade của package manager/installer, cần cấu hình và test |
| Công cụ native installer bổ sung | Thường không cần | Có thể cần WiX, các công cụ `deb/rpm` hoặc công cụ macOS |
| Mục đích thường gặp | QA launcher/runtime, bản chạy từ thư mục, bước trung gian | Phát hành cài đặt cho người dùng cuối, doanh nghiệp |
| Chạy trên mọi OS? | **Không**: launcher/runtime theo platform/architecture | **Không**: package theo nền tảng |

**Một ngộ nhận quan trọng trên Windows:** `HelloTool.exe` nằm **bên trong thư mục app image** là **application launcher**. Còn `.exe` được tạo bởi `jpackage --type exe` là **bộ cài Windows**. Chỉ nhìn phần mở rộng `.exe` không đủ để kết luận file là launcher hay installer.

**Một chi tiết trên macOS:** `HelloTool.app` là **application bundle**. File `.dmg` là **disk image** phân phối, thường chứa app để người dùng kéo vào Applications; nó không nhất thiết có trình hướng dẫn cài đặt như `.pkg`. Vì vậy hai định dạng `dmg` và `pkg` cùng thuộc đầu ra native của `jpackage` nhưng **cách sử dụng không giống hệt nhau**.

## 3. Application image bao gồm những gì?

`jpackage` kết hợp ứng dụng đã build với launcher và runtime. Cấu trúc cụ thể phụ thuộc OS và phiên bản công cụ.

### Windows

~~~text
dist/
└── HelloTool/
    ├── HelloTool.exe       # Application launcher
    ├── app/
    │   ├── HelloTool.jar   # Application payload
    │   └── HelloTool.cfg   # Launcher configuration
    └── runtime/            # Bundled Java runtime
~~~

Chạy `dist\HelloTool\HelloTool.exe` có thể khởi động app ngay từ image. **Không cần chạy installer** để dùng thư mục app image đã được tạo và chuyển đến môi trường tương thích.

### Linux

~~~text
HelloTool/
├── bin/
│   └── HelloTool           # Linux launcher
└── lib/
    ├── app/
    │   ├── HelloTool.jar
    │   └── HelloTool.cfg
    └── runtime/
~~~

Tên `app-image` của `jpackage` **không có nghĩa** tự tạo một file có đuôi `.AppImage` thuộc dự án đóng gói AppImage của Linux. Đây là hai khái niệm khác nhau; đầu ra `jpackage --type app-image` thường là **một thư mục**.

### macOS

~~~text
HelloTool.app/
└── Contents/
    ├── Info.plist
    ├── MacOS/             # Launcher
    ├── Resources/
    ├── app/               # Application payload
    └── runtime/           # Bundled Java runtime
~~~

Các cấu trúc trên minh họa phần cốt lõi theo tài liệu Oracle; thực tế có thể có thêm files/directories. Không phụ thuộc vào mọi đường dẫn nội bộ chưa được bảo đảm ổn định giữa các bản JDK.

### “Tự chứa” không đồng nghĩa “chạy mọi nơi”

Java runtime đi kèm giúp ứng dụng **không bắt buộc người dùng cài JDK riêng** chỉ để chạy app. Nhưng app image có **native launcher/runtime** cho hệ điều hành và kiến trúc CPU cụ thể. Ứng dụng có thể vẫn phụ thuộc thư viện native, API hệ thống, cấu hình TLS, font, driver, quyền truy cập hoặc tài nguyên bên ngoài. Vì vậy phải smoke test trên nền tảng đích, không copy một image Windows sang macOS rồi cho rằng sẽ chạy.

## 4. Native installer/package bổ sung điều gì?

Khi tạo native package, `jpackage` sử dụng **application image** và đưa nó vào **hình thức phân phối mà hệ điều hành hiểu được**. Sự khác biệt thể hiện ở việc người dùng mở/cài artifact như thế nào.

| Nền tảng | Định dạng `--type` | Ý nghĩa |
| --- | --- | --- |
| Windows | `exe` | Bộ cài Windows dạng executable |
| Windows | `msi` | Windows Installer package |
| Linux Debian/Ubuntu | `deb` | Gói tương tác với công cụ quản lý Debian |
| Linux RPM-based | `rpm` | Gói tương tác với hệ sinh thái RPM |
| macOS | `pkg` | Gói cài đặt macOS |
| macOS | `dmg` | Ảnh đĩa phân phối app/bundle |

Có thể cấu hình metadata và tích hợp OS như `--app-version`, `--vendor`, `--description`, `--install-dir`, shortcut/menu/file associations theo các option được hỗ trợ cho nền tảng đó.

**Không hứa quá mức:** native installer không tự tạo auto-updater, không tự ký số, không mặc định đảm bảo phần mềm được notarize trên macOS và không tự bảo đảm upgrade/uninstall giữ hoặc xóa đúng dữ liệu người dùng. Những yêu cầu này cần thiết kế và thử nghiệm riêng.

### Hạn chế về môi trường build

**`jpackage` không hỗ trợ tạo native package cho một OS từ OS khác bằng cách đổi `--type`.**

- Windows build `exe`/`msi`.
- Linux build `deb`/`rpm` với toolchain thích hợp.
- macOS build `dmg`/`pkg`.

Nếu muốn phát hành cho ba hệ điều hành, pipeline CI cần runner hoặc build environment tương ứng. Cùng một source/JAR có thể làm input cho nhiều pipeline, nhưng **artifact native không dùng chung cho các OS**.

## 5. Ví dụ hoàn chỉnh: Java class → JAR → app image trên Windows

Ví dụ sau biên dịch bằng API Java 17, tạo JAR có main class, dùng `jpackage` tạo app image rồi chạy launcher.

Tạo file **`HelloTool.java`**:

~~~java
public class HelloTool {
    public static void main(String[] args) {
        System.out.println("Hello from app image");
        System.out.println("args=" + args.length);
    }
}
~~~

Dùng PowerShell trên **Windows** với các lệnh `javac`, `jar`, `jpackage` có trong `PATH`. Trong thư mục chứa file `HelloTool.java`, tạo các thư mục build và compile:

~~~powershell
New-Item -ItemType Directory -Force -Path classes, input, dist
javac --release 17 -encoding UTF-8 -d classes .\HelloTool.java
jar --create --file .\input\HelloTool.jar --main-class HelloTool -C classes .
~~~

Tại đây:

- `--release 17` bảo đảm mã nguồn dùng đúng mức cú pháp/API Java 17 lúc biên dịch.
- `jar --main-class HelloTool` ghi entry point của ứng dụng vào JAR.
- Thư mục `input` chứa JAR sẽ được `jpackage` đưa vào application image.
- Thư mục `dist` là đích nhận **artifact**, không phải nơi nhập source files.

Tạo image; `--win-console` dành riêng cho **launcher console trên Windows**, để dễ thấy stdout của ứng dụng mẫu:

~~~powershell
jpackage --type app-image --name HelloTool --input .\input --main-jar HelloTool.jar --dest .\dist --win-console
~~~

Bây giờ chạy **launcher từ image**, không chạy `java -jar`:

~~~powershell
.\dist\HelloTool\HelloTool.exe sample
~~~

**Stdout được kiểm chứng trên Windows với JDK 24 khi Java class được compile bằng `--release 17`:**

~~~text
Hello from app image
args=1
~~~

Khi kiểm tra filesystem trong cùng phiên kiểm thử, các kết quả đều đúng:

~~~text
imageDirectoryExists=True
launcherExists=True
runtimeFileExists=True
Hello from app image
args=1
~~~

Trong test, `runtimeFileExists` được xác nhận bằng một native runtime file bên trong `runtime`. Đây là **bằng chứng image chứa runtime trên hệ thống kiểm thử**, không phải chỉ dẫn ứng dụng nên hardcode đường dẫn của file runtime nội bộ.

**Quan trọng:** bài đã kiểm thử **tạo và chạy app image** trên Windows. Những lệnh tạo MSI/EXE installer ở phần tiếp theo là ví dụ dựa trên tài liệu API, không được tuyên bố là đã chạy thành công trên máy kiểm thử chưa có WiX.

### Cách smoke test một app image

1. Kiểm tra thư mục image tồn tại và launcher có thể chạy.
2. Chạy launcher trực tiếp trong môi trường sạch, không dựa vào `java.exe` từ JDK phát triển.
3. Kiểm tra bundled runtime chứa đủ modules để chạy tính năng thật.
4. Kiểm tra tham số ứng dụng, JVM options, icon, resource files và native libraries.
5. Kiểm tra hành vi trên đúng kiến trúc CPU/OS mục tiêu.
6. Không chỉnh sửa image sau khi đã được ký hoặc đóng gói nếu việc đó làm hỏng signature/integrity.

## 6. Hai workflow: tạo installer trực tiếp hoặc đi qua app image

### Workflow A — tạo native installer trực tiếp

Khi ứng dụng đã ổn định và không cần sửa image trung gian, gọi `jpackage` trực tiếp từ JAR. Ví dụ **Windows có WiX Toolset tương thích**:

~~~powershell
New-Item -ItemType Directory -Force -Path installers
jpackage --type msi --name HelloTool --input .\input --main-jar HelloTool.jar --app-version 1.0 --dest .\installers --win-menu --win-shortcut
~~~

Theo tài liệu, kết quả là một file `.msi` trong thư mục `installers` với metadata ứng dụng tương ứng. **Tên file thực tế** có thể tùy quy tắc jpackage/version/format; không hardcode khi không biết artifact được tạo. Lệnh này **chưa được chạy thử tại máy đang dùng** vì chưa có WiX trong `PATH`.

### Workflow B — tạo app image, kiểm thử, rồi chuyển thành installer

Workflow phù hợp khi cần kiểm tra/sửa image trước khi đóng gói:

~~~text
HelloTool.jar
    |
    v
jpackage --type app-image
    |
    v
dist/HelloTool/
launcher + app + runtime
    |
    | (QA và điều chỉnh image nếu cần)
    v
jpackage --type msi --app-image <image>
    |
    v
installers/*.msi
~~~

Ví dụ Windows:

~~~powershell
jpackage --type msi --name HelloTool --app-image .\dist\HelloTool --app-version 1.0 --dest .\installers --win-menu --win-shortcut
~~~

Trong lệnh trên:

- `--app-image` là **đường dẫn đến image đã dựng**, không phải đường dẫn đến JAR.
- `--name` được yêu cầu theo tài liệu khi đóng gói một image đã có.
- `--runtime-image` **không được dùng cùng `--app-image`** khi tạo package. Muốn thay runtime, phải chọn ở giai đoạn tạo app image trước đó.
- Các option liên quan cài đặt trên Windows chỉ có ý nghĩa tại bước tạo **native Windows package**.

**Lợi ích của hai giai đoạn:** nếu launcher hoặc runtime có lỗi, bạn có thể phát hiện ngay trên image trước khi mất thời gian build bộ cài và chạy cài/gỡ. Cũng có thể thêm tài nguyên hoặc điều chỉnh nội dung image có chủ đích trước bước đóng gói.

**Giới hạn:** test app image **không thay** test installer. Cần chạy gói trên máy thử thích hợp để kiểm tra quyền cài, đường dẫn, shortcut/menu, phiên bản nâng cấp, file associations và gỡ cài.

### Quan hệ chung

Ngay khi chạy lệnh tạo native installer trực tiếp, `jpackage` vẫn **tạo application image như một bước bên trong quy trình**. Workflow A chỉ không giữ image như artifact trung gian để QA riêng; workflow B giữ image để có thể test/chỉnh trước.

## 7. Prerequisites theo nền tảng và các ví dụ chưa chạy thử

Tạo app image và tạo installer **không có cùng prerequisite**:

| Nền tảng | Native format | Toolchain bổ sung cần xem xét |
| --- | --- | --- |
| Windows | `exe, msi` | **WiX Toolset** bản tương thích với JDK; tài liệu Oracle mô tả yêu cầu WiX |
| Linux Debian/Ubuntu | `deb` | Công cụ `deb`; hướng dẫn Oracle nhắc `fakeroot` trong môi trường Ubuntu |
| Linux RPM-based | `rpm` | Công cụ `rpm`; hướng dẫn Oracle nhắc `rpm-build` với Red Hat |
| macOS | `dmg, pkg` | Công cụ đóng gói macOS; Xcode command-line tools trong một số trường hợp ký hoặc custom icon DMG |

Nếu app image thành công nhưng build MSI thất bại vì thiếu WiX, **đó là lỗi toolchain đóng gói**, không phải mặc nhiên lỗi mã Java. Phiên bản WiX phù hợp có thể khác theo bản JDK: hãy xem tài liệu của **đúng JDK dùng chạy `jpackage`**.

Các lệnh tham chiếu cho môi trường khác Windows:

~~~bash
# Trên Linux có công cụ Debian packaging:
jpackage --type deb --name HelloTool --input input --main-jar HelloTool.jar --dest installers

# Trên Linux có công cụ RPM packaging:
jpackage --type rpm --name HelloTool --input input --main-jar HelloTool.jar --dest installers

# Trên macOS:
jpackage --type dmg --name HelloTool --input input --main-jar HelloTool.jar --dest installers

# Trên macOS:
jpackage --type pkg --name HelloTool --input input --main-jar HelloTool.jar --dest installers
~~~

Đây là **các lệnh theo tài liệu**, không phải stdout đã xác nhận trên Linux/macOS. Chúng giả định JAR và dependencies phù hợp đã có, công cụ packaging đã cài và đang chạy trên OS tương ứng. Không thể chạy `--type deb` trên máy Windows để nhận Linux package theo cơ chế hỗ trợ chính thức.

## 8. Phân biệt app image với runtime image của jlink

Có ba tầng khác nhau, rất dễ gọi nhầm:

~~~text
JAR / modules
      |
      |   + Java runtime image từ jlink
      v   v
Application image (app + launcher + runtime)
      |
      +--> Chạy trực tiếp (app-image)
      |
      +--> Native installer (msi/exe/deb/rpm/dmg/pkg)
~~~

- `jlink` tạo **runtime image** theo Java modules. Runtime này chưa tự trở thành ứng dụng của bạn, chưa phải native installer.
- `jpackage --type app-image` kết hợp **app + runtime + launcher** thành application image.
- `jpackage --type msi` hoặc các native types khác tạo artifact phân phối/cài đặt **dựa trên app image**.
- `--runtime-image <directory>` đưa vào runtime image do bạn chuẩn bị trước, ví dụ tạo bằng `jlink`.
- Nếu không chỉ định runtime image, `jpackage` thường sử dụng `jlink` để tạo runtime theo cấu hình app/modules.

**Ví dụ về hai quyết định khác nhau:** khi chạy `javac --release 17` bằng JDK 24, class file được biên dịch cho Java 17; nhưng nếu `jpackage` được chạy bằng JDK 24 mà không truyền `--runtime-image`, runtime đi kèm có thể được tạo từ JDK 24. Không suy ra version runtime từ cờ `--release` của `javac`.

Một lưu ý còn áp dụng hiện nay: theo hướng dẫn Oracle JDK 25, runtime do `jpackage` tạo không còn tự động đưa **service bindings** vào giống một số phiên bản trước. Nếu ứng dụng dùng service provider modules, kiểm tra nội dung runtime và cân nhắc `--jlink-options --bind-services` theo đúng JDK đang dùng. Không nên suy luận app image chứa đủ modules chỉ vì JAR chạy thành công với một JDK đầy đủ trên máy phát triển.

**Khác với native compilation:** dù kết quả có launcher `.exe`, `jpackage` vẫn đóng gói Java runtime để chạy mã bytecode. Nó **không đồng nghĩa** tạo executable độc lập không cần JVM như các công cụ native compilation khác.

## 9. Phân phối và nâng cấp: những thứ người dùng nhận được

### App image

Nếu cung cấp cho người dùng một image chứa launcher/runtime, họ có thể giải nén/copy và chạy trong môi trường được hỗ trợ. Ứng dụng **không** mặc nhiên có entry trong danh sách ứng dụng cài đặt, shortcut desktop, registry cài đặt hoặc cơ chế uninstall. Quy trình cập nhật có thể là thay thư mục image theo hướng dẫn hoặc một updater riêng của sản phẩm.

Vì không có installer quản lý vòng đời, hãy quyết định rõ **nơi lưu dữ liệu người dùng**. Không nên tự mặc định mọi môi trường cho phép ghi tùy ý ngay vào thư mục image; việc đổi version có thể làm mất dữ liệu nếu bạn để dữ liệu người dùng trong thư mục được thay thế.

### Native package

Người dùng cài theo cơ chế của OS, có thể có shortcut/menu, thư mục cài, metadata version và phương thức gỡ cài theo format. Nhưng **không** tự có auto-update, không tự bảo đảm nâng cấp giữ lại mọi dữ liệu, và không tự ký số.

Ví dụ:

- Windows MSI hỗ trợ mô hình cài đặt và nâng cấp do Windows Installer quản lý, nhưng phải cấu hình version/upgrade identity và test.
- Debian/RPM package được quản lý qua package tools của hệ điều hành, nhưng cách cài/gỡ/nâng cấp còn phụ thuộc scripts/dependencies và chính sách gói.
- macOS DMG thường là kênh phân phối chứa app để người dùng di chuyển; PKG thường đi theo installer workflow.

Do đó nên chọn format theo **trải nghiệm người dùng và vận hành**, không chỉ dựa trên việc một lệnh `jpackage` có chạy thành công không.

## 10. Test gì trước khi phát hành?

| Đối tượng | Bài test phù hợp |
| --- | --- |
| JAR và bytecode | Unit/integration tests; chạy khi có JDK phát triển |
| App image | Có launcher? Có runtime? Chạy trên OS/CPU mục tiêu? Resource paths, modules, JVM options đúng? |
| Native installer | Package cài được? Bản được cài chạy được? Đường dẫn, quyền, shortcut, menu, version, uninstall đúng? |
| Nâng cấp | Cài version trước rồi upgrade; xử lý config/dữ liệu cũ đúng? |
| Bảo mật phân phối | Chữ ký, notarization nếu áp dụng; nguồn artifact và checksum được bảo vệ? |

Một quy trình phát hành có chất lượng thường là:

~~~text
build/test Java
  → tạo JAR/module
  → tạo app image
  → chạy launcher từ image và test runtime
  → tạo native package theo target OS
  → cài thử trên môi trường sạch
  → test app đã cài, upgrade và uninstall
  → phát hành qua kênh được quản lý
~~~

**Đừng chỉ test `java -jar`.** Một ứng dụng chạy được bằng JDK phát triển chưa đủ chứng minh launcher do `jpackage` tạo có đủ modules, đúng args hay đúng native dependencies. **Đừng chỉ test image** nếu sản phẩm cuối là MSI/DEB/PKG; việc cài đặt có thể phát sinh lỗi riêng mà image test không nhận ra.

## 11. Những lỗi nhận thức và lỗi cấu hình thường gặp

1. **Nghĩ `--type app-image` tạo trình cài.** Nó tạo image (thư mục/bundle) có launcher chạy được, không phải MSI/DEB/PKG.
2. **Nghĩ mọi file `.exe` đều là installer.** Launcher trong thư mục image và installer `--type exe` là hai artifact khác nhau.
3. **Nghĩ native installer nghĩa là Java đã được compile sang machine code.** Thường sai: JVM runtime vẫn có trong package.
4. **Nghĩ mọi `--type` có thể tạo trên mọi OS.** Sai: native package cần build trên nền tảng đích.
5. **Quên `--type` và nghĩ công cụ sẽ chọn app image.** Nếu bỏ option, `jpackage` có default package type phụ thuộc nền tảng; nên nêu rõ mong muốn.
6. **Nhầm `--input` và `--dest`.** `--input` là nơi JAR/resource đầu vào; `--dest` là nơi tạo artifact.
7. **Nhầm `--main-jar` và `--name`.** `--main-jar` là JAR chứa entry point; `--name` đặt tên ứng dụng/package.
8. **Cho rằng có image rồi sẽ có shortcut OS.** Copy/chạy thư mục image không thực thi bước cài đặt tạo shortcut/menu.
9. **Dùng `--app-image` và `--runtime-image` cùng nhau.** Cặp option này không tương thích trong trường hợp đóng gói từ image có sẵn.
10. **App image tạo được nhưng MSI không tạo được, kết luận mã Java lỗi.** Hãy kiểm tra WiX/toolchain và các điều kiện native installer.
11. **Nghĩ JVM runtime trong image là version đặt bởi `javac --release`.** Quyết định runtime thuộc bước đóng gói, không tự động theo target bytecode.
12. **Nghĩ app image chạy trên Windows sẽ chạy trên macOS.** Nó chứa launcher/runtime native theo OS/CPU.
13. **Nghĩ DMG luôn có installer wizard như PKG.** DMG là ảnh đĩa phân phối; thao tác người dùng khác PKG.
14. **Nghĩ có file MSI là đã test cài đặt thành công.** Cần thử install/launch/uninstall/upgrade trên máy mục tiêu.
15. **Không kiểm tra code signing và bảo mật nguồn phân phối.** `jpackage` không tự động giải quyết toàn bộ trust/signing/notarization.
16. **Tự hardcode cấu trúc nội bộ vào code nghiệp vụ.** Tổ chức app/runtime file có thể thay đổi; cần cách quản lý resource/paths phù hợp.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `jpackage --type app-image` tạo file MSI không?  
**Đáp án:** Không. Nó tạo thư mục/bundle ứng dụng có launcher và Java runtime.

**Câu 2.** `HelloTool.exe` nằm trong app image Windows là gì?  
**Đáp án:** Launcher để chạy ứng dụng; không phải tự động là file cài đặt `--type exe`.

**Câu 3.** Một app image chứa runtime rồi có chạy được trên mọi OS/CPU không?  
**Đáp án:** Không. Native launcher/runtime và các phụ thuộc hệ thống gắn với nền tảng build.

**Câu 4.** Nếu muốn QA image trước rồi mới tạo MSI, làm sao?  
**Đáp án:** `--type app-image`, chạy launcher/test image, rồi `--type msi --app-image <image> --name ...` ở Windows có WiX phù hợp.

**Câu 5.** Có thể dùng `--runtime-image` với `--app-image` trong cùng lệnh chuyển image thành installer không?  
**Đáp án:** Không. Chọn custom runtime ở bước tạo image.

**Câu 6.** Khi `jpackage --type msi` lỗi vì thiếu WiX, app image đã tạo chạy tốt có đồng nghĩa mã Java lỗi không?  
**Đáp án:** Không. Đây có thể là lỗi toolchain native packaging.

**Câu 7.** Có thể tạo `.dmg` trên Windows chỉ bằng cách đổi `--type` không?  
**Đáp án:** Không. Native packages phải build trên OS tương ứng.

**Câu 8.** `jlink` tạo app installer hay chỉ runtime image?  
**Đáp án:** Chỉ tạo Java runtime image; `jpackage` tạo app image và native package.

**Câu 9.** Tạo MSI xong có chắc auto-update và code signing không?  
**Đáp án:** Không. Upgrade policy, auto-update, signature và quy trình phát hành cần xây dựng riêng.

**Câu 10.** Test `java -jar` thành công đã đủ xác nhận bản cài đặt chạy ổn chưa?  
**Đáp án:** Chưa. Cần test launcher của image và bản đã cài trên OS mục tiêu.

## Tài liệu chính thức

- Oracle JDK 25 — **jpackage Command**: các format `app-image, exe, msi, deb, rpm, pkg, dmg`, cú pháp `--app-image` và `--runtime-image`, quy tắc build theo OS: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html
- Oracle JDK 25 — **Packaging Overview**: cấu trúc app image Windows/Linux/macOS, prerequisite native packaging, Java runtime và thay đổi service bindings từ JDK 25: https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html
- Oracle JDK 25 — **Image and Runtime Modifications**: workflow hai bước, `--name` khi tạo package từ image, `--app-image` không dùng chung `--runtime-image`: https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html
- Oracle JDK 26 — **Packaging Tool User's Guide**: tài liệu hướng dẫn đóng gói hiện hành: https://docs.oracle.com/en/java/javase/26/jpackage/index.html
- Oracle JDK 17 — **jpackage Command**: lệnh và cú pháp cho Java 17+: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html
- OpenJDK JEP 392 — **Packaging Tool**: tính năng chính thức từ Java 16: https://openjdk.org/jeps/392