# Tài nguyên tùy chỉnh cho gói cài đặt với jpackage (Java 16+)

## 1. Mục tiêu và ngữ cảnh

Khi phân phối ứng dụng Java tới người dùng, một gói cài đặt native cần nhiều thứ hơn JAR và JVM: icon, tên phần mềm, giấy phép, tài nguyên dữ liệu, liên kết file, các màn hình trình cài, metadata và đôi khi có script chạy trong lúc cài/gỡ. Công cụ **`jpackage`** có thể tạo **application image** hoặc package cài đặt theo từng hệ điều hành, đồng thời cung cấp cách thay thế các tài nguyên đóng gói mặc định.

**Đề bài tập trung vào tài nguyên tùy chỉnh cho gói cài đặt**, đặc biệt là `--resource-dir`: một thư mục chứa những **file override có tên được công cụ `jpackage` nhận biết**. Cần hiểu chính xác khi nào dùng thư mục này, khi nào dùng tùy chọn dòng lệnh `--icon`, `--license-file`, `--file-associations`, `--app-content`, và khi nào phải sửa template native.

`jpackage` xuất hiện ở dạng incubating trong Java 14 và trở thành **công cụ chính thức ở Java 16** (JEP 392). Bài này dùng cơ chế **vẫn áp dụng trong Java 17, 21, 25 và các JDK hiện đại**, không hướng dẫn sử dụng module `jdk.incubator.jpackage` đã lỗi thời.

### Cần phân biệt package và app image

- **Application image (`--type app-image`):** thư mục chứa launcher, JAR/module, tài nguyên và runtime Java; đây **chưa phải** MSI/EXE, DEB/RPM hoặc PKG/DMG installer.
- **Native installer (`--type msi/exe/deb/rpm/pkg/dmg`):** gói theo định dạng của OS, có thêm metadata, UI, quyền, lifecycle cài đặt/gỡ cài.
- **Launcher:** executable của ứng dụng trong app image, không đồng nghĩa chính file installer.
- **Resource override:** tài nguyên được `jpackage` dùng khi **build**, không nhất thiết tồn tại dưới dạng file riêng trong thư mục ứng dụng sau cài.

`jpackage` đóng gói **cho hệ điều hành hiện tại**, không tự cross-package Windows MSI trên Linux hoặc macOS DMG trên Windows. Để kiểm thử native installer, cần runner và toolchain đúng OS.

## 2. Bốn cơ chế dễ nhầm: `--resource-dir`, `--icon`, `--input`, `--app-content`

| Nhu cầu | Cờ phù hợp | Ý nghĩa |
| --- | --- | --- |
| Đổi một template/script/hình nền mà `jpackage` dùng khi build | `--resource-dir DIR` | Tra các **tên tài nguyên được quy định** theo OS và loại package |
| Đổi icon, tên, version, mô tả, license | `--icon`, `--name`, `--app-version`, `--description`, `--license-file` | Tùy chọn command line chuẩn, ưu tiên khi đáp ứng được nhu cầu |
| Đưa JAR, file cấu hình và tài liệu đi kèm ứng dụng | `--input DIR`, `--app-content FILE_OR_DIR` | Payload trong application image |
| Đăng ký định dạng tài liệu với chương trình | `--file-associations PROPERTIES` | Cấu hình loại file để launcher mở |

**Ví dụ:**
- `overrides/CustomPackDemo.ico` có thể là **icon override** nhận qua `--resource-dir`.
- `app-content/NOTICE.txt` là **dữ liệu ứng dụng**, nên dùng `--app-content`.
- `LICENSE.txt` để installer hiển thị các điều khoản cần truyền bằng `--license-file`.
- `main.wxs` để đổi cấu trúc installer Windows là **template WiX**, chỉ dùng khi thực sự cần tùy biến chuyên sâu.

**Không đặt một file bất kỳ vào `--resource-dir` rồi mong nó được copy vào ứng dụng.** Công cụ chỉ tìm những tên resource được định nghĩa. Với phần lớn tùy chỉnh đơn giản, cờ chính thức thường rõ ràng và ổn định hơn sửa template.

## 3. `--resource-dir` hoạt động thế nào?

Cú pháp chung:

```text
jpackage ... --resource-dir path-to-resources
```

Dấu `...` là **ký hiệu rút gọn**, không phải lệnh độc lập. Tham số là **đường dẫn tới thư mục**, tuyệt đối hoặc tương đối với thư mục làm việc. `jpackage` tìm các file có **tên đúng với launcher/package và hệ điều hành đang build**. Khi tìm thấy file được nhận dạng, công cụ sử dụng phiên bản custom để thay cho tài nguyên mặc định tương ứng.

Ví dụ trên Windows, ứng dụng tên `CustomPackDemo` có thể có:

```text
overrides/
  CustomPackDemo.ico
  main.wxs
  overrides.wxi
```

Tuy nhiên, **không cần có cả ba file**. Nếu chỉ muốn đổi icon thì một `CustomPackDemo.ico` hợp lệ đã đủ. `main.wxs` và `overrides.wxi` chỉ nên thêm khi thật sự cần sửa MSI/EXE và đã kiểm thử template của JDK hiện tại.

### Thứ tự ưu tiên

Theo tài liệu `jpackage` hiện hành, **trong phần lớn trường hợp option command line ghi đè tài nguyên trong `--resource-dir`**. Ví dụ nếu đã có một file icon được cung cấp qua `--icon`, đừng đồng thời dựa vào icon cùng tên trong thư mục resource mà không kiểm tra kết quả.

**Khuyến nghị:** ưu tiên `--icon`, `--description`, `--app-version`, `--vendor` hoặc option chuẩn phù hợp. Dùng `--resource-dir` cho những nội dung mà option chuẩn **không thể thể hiện**, như một template WiX đặc thù hay hình nền DMG riêng.

### Template override không phải file có thể rút gọn tùy ý

Nếu thay một template mặc định, bản tùy chỉnh **phải giữ đầy đủ các property/thành phần mà template gốc yêu cầu**. Với WiX/DEB/RPM/PKG, cắt bỏ những thành phần không hiểu có thể làm hỏng installer, nâng cấp hoặc gỡ cài.

Cách làm tốt là **copy template từ output build của đúng JDK/toolchain rồi thay đổi tối thiểu**, không tạo một file `main.wxs` 3 dòng và kỳ vọng trình cài hoạt động.

## 4. Tìm tên tài nguyên hợp lệ bằng `--verbose` và `--temp`

Hai cờ quan trọng:

```text
--verbose   Xuất log chi tiết quá trình build, gồm tài nguyên đang dùng
--temp DIR  Giữ các file trung gian trong thư mục mới hoặc rỗng
```

`--verbose` có thể ghi dòng gợi ý **tên file cần đặt vào `--resource-dir`**. `--temp` giúp bạn xem các file template, config và resource mà công cụ đã sinh, thay vì chỉ đoán từ tên.

Một quy trình:

1. Build phiên bản **mặc định** với `--verbose`; chỉ định một thư mục `--temp` mới.
2. Xem log các resource mặc định và tên file override mà JDK gợi ý.
3. Xem những template được giữ trong thư mục tạm khi thực sự cần thay.
4. Copy resource hợp lệ sang thư mục riêng, sửa theo yêu cầu, không làm mất thuộc tính bắt buộc.
5. Build lại với `--resource-dir` và `--verbose`.
6. Xác nhận log báo **Using custom package resource** cho file mong đợi.
7. Kiểm thử app image hoặc installer thực tế, không dừng ở việc build trả exit code 0.

**Phân biệt đường dẫn:**

- `--resource-dir` = thư mục **đầu vào** của resource override.
- `--temp` = thư mục **kết quả trung gian** của quá trình build.
- `--dest` = nơi đặt **artifact cuối** (image hoặc package).
- `--input` = thư mục payload chứa JAR và file ứng dụng.

Không sửa trực tiếp file trong `--temp` rồi mặc định lần build sau sẽ dùng lại nó. Khi muốn dùng một phiên bản đã chỉnh, cung cấp qua `--resource-dir`.

## 5. Ví dụ thực hành có thể chạy: custom icon và dữ liệu đi kèm trên Windows

Ví dụ này dùng **`javac --release 17` và công cụ `jpackage` của JDK hiện đại**, tạo một **app image trên Windows**. Nó thực sự kiểm tra `--resource-dir`, launcher và `--app-content`. Nó **không tự động tạo MSI/EXE installer**, vì các gói đó còn cần WiX.

### 5.1. Java source

Tạo file **`CustomPackDemo.java`**:

```java
public class CustomPackDemo {
    public static void main(String[] args) {
        System.out.println("launcher=CustomPackDemo");
        System.out.println(
                "args=" + java.util.Arrays.toString(args));
    }
}
```

Chương trình dùng `Arrays.toString(args)` để thấy các tham số mà packaged launcher thực sự chuyển tới `main`.

### 5.2. Build JAR và tạo tài nguyên

Chạy trong **Windows PowerShell** tại thư mục demo riêng:

```powershell
New-Item -ItemType Directory -Force -Path input, classes, out, overrides, extra, temp | Out-Null
javac --release 17 -encoding UTF-8 -d classes CustomPackDemo.java
jar --create --file input\CustomPackDemo.jar --main-class CustomPackDemo -C classes .
Set-Content -Path extra\NOTICE.txt -Value "Additional application payload (not an installer template)."
```

Ở đây `NOTICE.txt` là **payload** có ích khi ứng dụng được phát hành, không phải một template installer. Nó được đưa vào `extra` để minh họa `--app-content`.

Để ví dụ tự khép kín, tạo **ICO thật** từ icon hệ thống Windows bằng `System.Drawing` (không đổi tên một file PNG thành ICO):

```powershell
Add-Type -AssemblyName System.Drawing
$iconPath = Join-Path overrides "CustomPackDemo.ico"
$iconStream = [System.IO.File]::Create($iconPath)

try {
    [System.Drawing.SystemIcons]::Information.Save($iconStream)
} finally {
    $iconStream.Dispose()
}
```

Icon này chỉ nhằm **kiểm tra cơ chế override**. Khi phát hành, hãy dùng artwork có quyền sử dụng, đủ kích thước/độ phân giải và được thiết kế phù hợp thương hiệu.

### 5.3. Tạo app image với icon override

```powershell
jpackage --type app-image --name CustomPackDemo --input input --main-jar CustomPackDemo.jar --main-class CustomPackDemo --resource-dir overrides --app-content extra --dest out --temp temp --verbose --win-console
```

Vai trò từng phần:

- `--type app-image` tạo **thư mục ứng dụng**, chưa phải MSI/EXE installer.
- `--name CustomPackDemo` xác định tên launcher.
- `--input input` và `--main-jar CustomPackDemo.jar` đưa JAR vào image.
- `--resource-dir overrides` cho phép nhận **`CustomPackDemo.ico`** theo tên launcher.
- `--app-content extra` đưa `NOTICE.txt` vào payload ứng dụng.
- `--temp temp` giữ resource trung gian để có thể kiểm tra.
- `--verbose` in thông tin chọn resource.
- `--win-console` là tùy chọn **chỉ trên Windows** giúp launcher CLI có console.

Tạo image tại `out\CustomPackDemo`. Nếu đã có thư mục output cùng tên, hãy dùng một output mới hoặc chủ đích dọn đúng artifact build cũ trước khi chạy lại. Không coi `jpackage` là phép cập nhật trực tiếp một image đã tạo.

### 5.4. Kiểm tra bằng launcher thật

```powershell
.\out\CustomPackDemo\CustomPackDemo.exe hello
```

**Standard output đã kiểm thử:**

```text
launcher=CustomPackDemo
args=[hello]
```

Với `--verbose`, lần thử thực tế trên JDK 24 Windows hiển thị:

```text
Using custom package resource [icon] (loaded from CustomPackDemo.ico).
```

Đây là bằng chứng **`jpackage` đã chọn icon custom**, không chỉ vì chúng ta đặt file vào folder. File icon được giữ trong thư mục `--temp` trùng SHA-256 với icon nguồn, và `NOTICE.txt` cũng có mặt trong app image.

Có thể tự xem:

```powershell
Get-ChildItem -Path out\CustomPackDemo -Recurse -File -Filter NOTICE.txt
Get-ChildItem -Path temp -Recurse -File -Filter CustomPackDemo.ico
```

**Phạm vi kiểm chứng:** Chương trình trên đã build app image và chạy launcher thực. Nó **chưa chứng minh các template MSI, EXE, DEB, RPM, DMG, PKG đã được build**, vì chúng cần toolchain/cấu hình riêng và test trên đúng OS.

## 6. Những tài nguyên tùy chỉnh trên Windows MSI/EXE

Windows installer dùng hệ thống template/nguồn có liên quan tới **WiX Toolset**. Khi `--type msi` hoặc `--type exe`, những tài nguyên thường gặp trong `--resource-dir` gồm:

| Tên tài nguyên | Công dụng |
| --- | --- |
| `main.wxs` | Source WiX chính để tạo MSI |
| `overrides.wxi` | Các biến/override cho file WiX |
| `CustomPackDemo-post-image.wsf` | Hook sau khi dựng app image, trước giai đoạn tạo MSI |
| `CustomPackDemo.ico` | Icon của launcher `CustomPackDemo` |
| `CustomPackDemo.properties` | Template properties của launcher executable |
| `InstallDirNotEmptyDlg.wxs` | Template UI liên quan kiểm tra install directory |
| `ShortcutPromptDlg.wxs` | Template UI cho việc lựa chọn shortcut |
| `CustomPackDemo-post-msi.wsf` | Hook sau khi tạo MSI nhúng trong quy trình EXE installer |
| `WinInstaller.properties` | Template thuộc EXE installer wrapper |

**Không phải mọi resource đều được dùng trong mọi kiểu build**. Những hook như `-post-msi.wsf` chỉ có ý nghĩa với quy trình installer tương ứng; file `CustomPackDemo.ico` dùng được cả ở cấp launcher/app image.

### Khi nào nên chọn cờ chuẩn thay vì WiX template?

Nếu nhu cầu chỉ là thông tin ứng dụng hoặc shortcut:

```text
--name CustomPackDemo
--app-version 1.0
--vendor "Example Vendor"
--description "Demo Java application"
--icon path-to-icon.ico
--license-file LICENSE.txt
--win-menu
--win-shortcut
--win-dir-chooser
```

Đây là **danh sách option** (không phải command đầy đủ). `--win-menu`/`--win-shortcut`/`--win-dir-chooser` là Windows-only. Chỉ sửa `main.wxs` khi có yêu cầu thật sự vượt những cờ được hỗ trợ, và phải test cài/gỡ/nâng cấp sau đó.

### Ví dụ tạo MSI có điều kiện

Sau khi đã tạo JAR và có giấy phép sản phẩm hợp lệ:

```powershell
jpackage --type msi --name CustomPackDemo --input input --main-jar CustomPackDemo.jar --main-class CustomPackDemo --dest installers --resource-dir overrides --app-version 1.0 --license-file LICENSE.txt --win-menu --win-shortcut --verbose
```

**Đây là lệnh minh họa cho máy Windows có WiX phù hợp, không phải một MSI đã được kiểm thử tại đây.** Môi trường thực hành của bài **không có lệnh `wix`, `candle` hoặc `light` trên `PATH`**; vì vậy chỉ phần build `--type app-image` được thực hiện thành công. Nếu MSI build thất bại do không tìm được WiX, lỗi đó **không tự chứng minh `--resource-dir` sai**.

Để tạo installer thật cần cài và xác nhận toolchain theo yêu cầu JDK, cung cấp `LICENSE.txt` thật, build package, sau đó cài/gỡ trên **máy test/VM**. Không cài thử MSI lên máy production chỉ để kiểm tra template.

### Template WiX phải theo đúng bản toolchain

Không tạo `main.wxs` hay `overrides.wxi` ngắn vài dòng rồi giả định là đủ. Một file WiX có thể chứa nhiều thành phần: directory tree, component IDs, UI, feature, shortcuts, điều kiện install/upgrade. Nếu thay không đầy đủ, MSI có thể build thất bại hoặc cài/gỡ sai.

Quy trình nên là: build mặc định với `--verbose`/`--temp`, lấy file default của **chính JDK**, sửa tối thiểu, xây lại với `--resource-dir`, test install/uninstall và review mỗi lần nâng JDK/WiX.

## 7. Linux DEB và RPM: template metadata và lifecycle script

Tên resource phụ thuộc hệ điều hành, và Linux còn chia thành DEB/RPM. Trong manual `jpackage` Java 25:

| Phạm vi | Tên file ví dụ | Ý nghĩa |
| --- | --- | --- |
| Launcher Linux | `CustomPackDemo.png` | Icon PNG của launcher |
| Desktop integration | `CustomPackDemo.desktop` | Desktop entry theo launcher |
| DEB | `control` | Metadata control |
| DEB | `copyright` | Tài liệu bản quyền |
| DEB | `preinstall`, `postinstall` | Hook trước/sau cài |
| DEB | `prerm`, `postrm` | Hook trước/sau gỡ |
| RPM | `package-name.spec` | Spec của gói RPM, đổi thành tên package thực tế |

**Đặc biệt chú ý tên file:** Một số tài liệu Debian hoặc hướng dẫn jpackage cũ sử dụng tên `preinst`, nhưng **manual jpackage Java 25** liệt kê **`preinstall`** là tên file template để override. Tên file của resource-dir phải theo JDK đang chạy, không tự đổi theo tên script native nếu `jpackage` mong đợi tên khác.

Nếu chỉ cần icon hoặc shortcut, cân nhắc `--icon`, `--linux-shortcut` và các cờ `--linux-*` phù hợp trước khi can thiệp file `.desktop` hoặc `.spec`.

**Script cài/gỡ có hệ quả bảo mật:** không hardcode quyền root tùy tiện, không tự ý xóa dữ liệu người dùng, không dùng mật khẩu trong script, không phụ thuộc network không kiểm soát. Kiểm thử trên distro mục tiêu, gồm install lần đầu, upgrade, cài lại và uninstall.

## 8. macOS PKG và DMG: icon, hình nền, plist và script

macOS phân biệt app bundle, PKG installer và DMG image. Những resource trong manual `jpackage` Java 25:

| Phạm vi | Tên ví dụ | Công dụng |
| --- | --- | --- |
| Launcher | `CustomPackDemo.icns` | Icon launcher macOS |
| App bundle | `Info.plist` | Metadata app |
| Runtime | `Runtime-Info.plist` | Metadata Java runtime |
| PKG/DMG | `CustomPackDemo-post-image.sh` | Script sau tạo app image |
| PKG | `preinstall`, `postinstall` | Hook cài đặt |
| PKG | `CustomPackDemo-background.png` | Hình nền Light Mode |
| PKG | `CustomPackDemo-background-darkAqua.png` | Hình nền Dark Mode |
| DMG | `CustomPackDemo-dmg-setup.scpt` | Script thiết lập DMG |
| DMG | `CustomPackDemo-background.tiff` | Background DMG |
| DMG | `CustomPackDemo-volume.icns` | Icon volume DMG |
| DMG | `CustomPackDemo-license.plist` | Template license DMG |

Nếu thay `Info.plist` hoặc entitlements, phải giữ các khóa hệ thống yêu cầu. Một plist thiếu trường hoặc sai định dạng có thể khiến macOS không nhận app, không cho ký hoặc không chạy đúng.

**Không nhầm ảnh với phần mở rộng:** `.icns`, `.png` và `.tiff` là các định dạng riêng. Đổi tên file JPEG thành TIFF không tạo TIFF hợp lệ. Dùng công cụ chuyển đổi ảnh phù hợp, kiểm tra cả Light/Dark Mode khi có hai background.

**Tùy chỉnh installer không thay cho code signing/notarization.** Với bản phân phối macOS thật, còn cần kiểm tra chính sách Gatekeeper, bundle signing, chữ ký gói và quyền, theo yêu cầu kênh phát hành.

## 9. License, file associations và tài nguyên đi kèm

### 9.1. `--license-file`

Nếu installer cần hiển thị điều khoản sử dụng, `jpackage` hỗ trợ:

```text
--license-file LICENSE.txt
```

Đây là cờ cấp **installer**, không đồng nghĩa đặt `LICENSE.txt` tùy ý trong `--resource-dir`. Trên Windows/macOS, nó có thể phục vụ giao diện yêu cầu người dùng chấp nhận điều khoản theo cơ chế trình cài. Một file license **chỉ dùng để trình cài hiển thị** không nhất thiết tự được đưa vào thư mục ứng dụng sau cài.

Nếu người dùng cần đọc lại license sau cài, đưa **bản tài liệu đó vào payload** bằng `--input` hoặc `--app-content`, và kiểm tra file trong output. Nội dung license cần được chủ sở hữu sản phẩm phê duyệt; không sử dụng một mẫu văn bản kỹ thuật thay cho thỏa thuận pháp lý.

### 9.2. `--file-associations`

Muốn hệ điều hành liên kết loại file với ứng dụng, có thể tạo tệp **`associations.properties`**:

```properties
extension=ldemo
mime-type=application/x-launch-demo
description=Launch Demo document
```

Rồi thêm option:

```text
--file-associations associations.properties
```

`jpackage` nhận các key `extension`, `mime-type`, `icon` và `description`. Ví dụ bỏ key `icon` để không đưa đường dẫn icon giả. Khi cần icon association, chỉ rõ một file thực đúng định dạng OS và kiểm tra sự tương thích.

Lưu ý: `--file-associations` không phải resource được tự tìm bởi `--resource-dir`. Khi test installer thật, cần thử double-click tài liệu `.ldemo` và xác nhận ứng dụng xử lý input path, hành vi default app và uninstall hợp lý.

### 9.3. `--input` và `--app-content`

Dữ liệu runtime như file cấu hình, ảnh, hướng dẫn, mẫu dữ liệu… nên được đóng gói như **payload**:

```text
input/
  CustomPackDemo.jar
  config/defaults.properties

extra/
  NOTICE.txt
```

`--input input` cho công cụ biết payload cơ sở; `--app-content extra` bổ sung tài liệu/thư mục vào application image. Cách này khác bản chất với resource override.

**Không đóng gói secret**, token hoặc dữ liệu riêng tư trong các tệp này. App image và installer có thể được mở và xem nội dung bởi người nhận.

## 10. Override template phức tạp: quy trình có khả năng bảo trì

Một template như `main.wxs`, `control`, `package-name.spec` hoặc `Info.plist` liên quan trực tiếp đến hành vi installer. Khi cần sửa:

1. **Xác nhận yêu cầu**: không có cờ chuẩn nào đáp ứng được?
2. **Chọn đúng platform/format và JDK**; không copy template Windows sang Linux.
3. **Build bản mặc định** cùng JDK, thu log `--verbose` và file từ `--temp`.
4. **Copy nguyên template phù hợp**, không bỏ nội dung chưa hiểu.
5. **Thay đổi tối thiểu**, có diff và ghi chú lý do.
6. **Đặt đúng tên trong `--resource-dir`**; tên launcher và package phải khớp.
7. **Build và xem log** có nhận resource custom không.
8. **Test output**: package metadata, image layout, icon, script và liên kết file.
9. **Cài/gỡ/nâng cấp thực** trên VM/sandbox, cả khi user đã có bản cũ.
10. **Review khi nâng JDK/toolchain** vì template của JDK mới có thể thay schema/biến/điều kiện build.

Không nên sửa file build tạm rồi đưa vào sản phẩm mà không có source version control; một thay đổi bị thất lạc sẽ khó tái lập lúc phát hành bản mới.

### `--temp` không phải nguồn cấu hình chính thức

`--temp` chỉ giữ output trung gian. Đừng sửa file trong đó sau khi build rồi tưởng đã thay bản phân phối. Những custom file thực sự cần được quản lý trong thư mục nguồn versioned và được truyền qua `--resource-dir` ở lần build mới.

### Cần quản lý tài nguyên theo OS

```text
packaging/
  windows/
    CustomPackDemo.ico
    overrides.wxi
  linux/
    CustomPackDemo.png
    CustomPackDemo.desktop
  macos/
    CustomPackDemo.icns
    CustomPackDemo-background.tiff
```

Sơ đồ trên là cách **tổ chức dự án tham khảo**, không phải bộ file bắt buộc. Chỉ copy resource thực sự cần dùng; không tạo template giả `overrides.wxi` hoặc ảnh giả chỉ để điền đủ sơ đồ.

## 11. Bảo mật và kiểm thử installer

Các tài nguyên như post-install script, WiX template, shell script, plist hay hình nền có thể được người dùng xem và đôi khi thực thi với đặc quyền trong quá trình cài. Vì vậy:

- **Review script trước khi phát hành**; không dùng hook để tải/runs mã không rõ nguồn, tắt bảo vệ OS hoặc sửa state ngoài yêu cầu.
- **Giữ quyền tối thiểu**; không đòi quyền administrator/root nếu installer không cần.
- **Không nhúng mật khẩu/token** trong `.wxs`, `.wxi`, `.properties`, script hay resource payload.
- **Thiết kế script idempotent** khi có thể; cài lại, upgrade và rollback phải xử lý được trạng thái đã tồn tại.
- **Giữ nguyên dữ liệu người dùng** khi uninstall trừ khi yêu cầu sản phẩm nêu rõ khác.
- **Ký và xác minh bản phát hành** theo chính sách OS; icon/logo/installer UI không bảo đảm mã thực thi an toàn.
- **Kiểm tra bản quyền hình ảnh** và điều khoản license của tài nguyên thương hiệu.
- **Kiểm tra file associations** không chiếm một extension phổ biến trái mong đợi người dùng.
- **Không để lộ thư mục build tạm** chứa thông tin nhạy cảm; `--temp` giữ file sau build và cần lifecycle cleanup.

### Ba cấp QA

| Cấp | Kiểm tra |
| --- | --- |
| **A. Cú pháp và input** | Source/JAR hợp lệ, icon đúng format, resource-dir đúng tên, toolchain đủ, license/association tồn tại |
| **B. Kết quả build** | `jpackage` exit code 0, `--verbose` xác nhận override, artifact có payload/metadata và launcher chạy được |
| **C. Cài đặt thực tế** | Chạy installer trên OS đích, quan sát dialog/icon/license, shortcut, file association, upgrade, uninstall, quyền, dữ liệu |

**Mức B không thay thế mức C.** Một MSI có thể build thành công mà shortcut sai; một app image có launcher chạy được nhưng bộ cài thực tế chưa từng được tạo.

### Những lỗi điển hình

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Đưa `NOTICE.txt` vào `--resource-dir` rồi mong nó có trong app | Không phải tên resource override | `--input`/`--app-content` |
| Đặt `icon.ico` thay vì `CustomPackDemo.ico` | Không khớp launcher | Dùng đúng tên hoặc `--icon` |
| Đổi đuôi PNG thành ICO mà không chuyển định dạng | Dữ liệu icon sai | Tạo ICO thực và test |
| Chỉ sửa `main.wxs` vài dòng | Thiếu cấu trúc WiX cần thiết | Copy template đầy đủ từ đúng JDK |
| Dùng template hướng dẫn Java 14 incubator trên JDK hiện đại | Tên/format có thể lỗi thời | Dùng manual và template JDK đang chạy |
| Tin `--resource-dir` được ưu tiên hơn `--icon` | Cờ trực tiếp thường có ưu tiên | Soát `--verbose` |
| Dùng `--temp` làm thư mục custom | Nó là vùng trung gian, không phải override input | `--resource-dir` |
| Nghĩ app image đã là installer native | Thiếu lifecycle cài/gỡ | Build package type tương ứng |
| Build MSI khi thiếu WiX | Thiếu dependency toolchain | Kiểm tra môi trường trước khi sửa resource |
| Tưởng `--license-file` cũng copy license vào app | Có thể chỉ phục vụ installer UI | Dùng payload nếu cần file sau cài |
| Copy template macOS sang Linux | Resource theo OS khác nhau | Tách thư mục theo OS |
| Hook installer thay đổi system không qua test | Có thể cài/gỡ lỗi hoặc gây hại | Test trong VM/sandbox và review |
| Chỉ xem log build, không cài thử | Không biết hành vi thật | Test install/update/uninstall |

## 12. Checklist triển khai

- [ ] Xác định đúng loại gói cần tạo: app image, MSI, EXE, DEB, RPM, PKG hay DMG?
- [ ] Build trên đúng OS và JDK hiện hành, không dùng `jdk.incubator.jpackage`?
- [ ] Đã phân biệt **template override** với **payload ứng dụng**?
- [ ] Với icon/license/metadata đơn giản, đã ưu tiên option chính thức?
- [ ] Các file trong `--resource-dir` có đúng tên được `jpackage` nhận biết không?
- [ ] Resource có đúng định dạng thật: ICO/PNG/ICNS/TIFF/WiX/plist/script?
- [ ] Template thay thế giữ toàn bộ thành phần bắt buộc của JDK/toolchain?
- [ ] `--verbose` xác nhận resource custom được tải?
- [ ] `--temp` được tạo đúng và có chính sách dọn dẹp?
- [ ] App image chứa JAR, runtime và payload đúng vị trí?
- [ ] Launcher thực sự chạy và nhận arguments đúng?
- [ ] Toolchain installer native được cài trước khi test package?
- [ ] License, shortcut, file association và script đã được kiểm tra trên OS đích?
- [ ] Không nhúng secret hoặc dữ liệu người dùng vào package?
- [ ] Build CI có khả năng tái lập và chạy test sau mỗi lần nâng JDK?
- [ ] Chữ ký/gói phân phối theo chính sách OS đã được kiểm chứng?

## 13. Câu hỏi tự kiểm tra

**1. Tại sao `--resource-dir` không phải lựa chọn đúng để đóng gói một file hướng dẫn bất kỳ?**

Vì nó chỉ cung cấp resource mà `jpackage` tìm bằng **tên đặc biệt**. Tài liệu cần có sau khi cài nên đưa qua `--input` hoặc `--app-content`.

**2. Nếu chỉ muốn thay icon launcher, có nhất thiết phải viết lại `main.wxs` không?**

Không. Dùng `--icon` hoặc file icon có đúng tên trong `--resource-dir`; sửa template WiX là không cần thiết.

**3. `--verbose` khác `--temp` ra sao?**

`--verbose` cho biết build đã chọn resource nào; `--temp` giữ các file trung gian để xem. Hai cờ có mục đích khác nhau.

**4. Windows app image có file `.exe` có đồng nghĩa đã có MSI installer không?**

Không. `.exe` trong app image là **launcher**. MSI/EXE installer phải build bằng loại package tương ứng và toolchain phù hợp.

**5. Vì sao không nên tạo `main.wxs` tối giản bằng vài dòng?**

Vì file override phải bảo toàn những thành phần/thuộc tính mà template default và WiX cần để tạo installer hợp lệ.

**6. Trên Linux DEB, nên lấy tên resource script trước cài từ đâu?**

Từ `jpackage --verbose` và **manual của JDK đang sử dụng**. JDK 25 liệt kê `preinstall` cho resource override; không đoán từ tài liệu cũ.

**7. `--license-file` và `--app-content` có cùng nhiệm vụ không?**

Không. `--license-file` chỉ giấy phép cho cơ chế installer. `--app-content` đưa file vào payload ứng dụng; dùng cả hai khi vừa cần trình bày license lúc cài vừa cần file ở máy sau cài.

**8. Một resource override được log là đã tải; vậy có thể coi gói đã sẵn sàng phát hành chưa?**

Chưa. Cần kiểm thử installer thật, vòng đời cài/nâng cấp/gỡ, bảo mật, quyền và signing trên nền tảng mục tiêu.

## 14. Tài liệu chính thức còn áp dụng

- [Oracle Java 25 — Override jpackage Resources](https://docs.oracle.com/en/java/javase/25/jpackage/override-jpackage-resources.html): cơ chế `--resource-dir`, priority và cách đọc `--verbose`/`--temp`.
- [Oracle Java 25 — The jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): danh sách cờ và tên resource Windows/Linux/macOS hiện hành.
- [Oracle Java 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): mục tiêu application image và installer native.
- [Oracle Java 25 — Manage the Installation](https://docs.oracle.com/en/java/javase/25/jpackage/manage-installation.html): license, thư mục cài và các lựa chọn installer.
- [Dev.java — jpackage](https://dev.java/learn/jvm/tool/jpackage/): tài liệu thực hành Java chính thức.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` chính thức từ Java 16.

**Ghi nhớ:** `--resource-dir` chỉ dùng để **ghi đè resource/template mà jpackage nhận biết**; `--input`/`--app-content` dùng cho **file ứng dụng**; `--icon`, `--license-file` và `--file-associations` là **option chuyên dụng** nên ưu tiên khi đủ đáp ứng. Luôn kiểm chứng tên resource bằng `--verbose`, dùng template của đúng JDK và test installer trên hệ điều hành đích.
