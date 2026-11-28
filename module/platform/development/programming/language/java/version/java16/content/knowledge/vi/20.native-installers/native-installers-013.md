# Phân biệt cài mới, nâng cấp và gỡ cài đặt trong kế hoạch kiểm thử

Một native installer có thể cài ứng dụng Java thành công trên máy sạch nhưng vẫn lỗi khi nâng cấp hoặc gỡ cài đặt. Bản nâng cấp có thể ghi đè cấu hình người dùng, để lại file cũ, chạy migration nhiều lần hoặc không khôi phục được khi quá trình cài bị gián đoạn. Gỡ cài đặt có thể xóa nhầm dữ liệu cần giữ lại hoặc để sót service, shortcut và package metadata.

Vì vậy, kiểm thử installer phải xem **cài mới**, **nâng cấp**, **gỡ cài đặt** và **cài lại** là các luồng riêng. Cần kiểm tra cả trạng thái package manager, file trên đĩa, tiến trình đang chạy, cấu hình, dữ liệu người dùng, quyền truy cập và khả năng phục hồi sau lỗi.

Trong module Java 16, **jpackage** là công cụ đóng gói ổn định và vẫn hữu ích trong Java hiện đại. Bài này tập trung vào kế hoạch kiểm thử vòng đời cho MSI/EXE trên Windows, PKG/DMG trên macOS, DEB trên Debian/Ubuntu và RPM trên Fedora/RHEL/openSUSE. Các ví dụ dùng công cụ hệ điều hành hiện hành.

## 1. Ba trạng thái vòng đời cần phân biệt

| Luồng | Trạng thái ban đầu | Hành động | Kết quả mong đợi |
|---|---|---|---|
| Cài mới | Ứng dụng chưa có trên máy | Cài package lần đầu | Có đúng file, launcher, shortcut, association, service và cấu hình mặc định theo thiết kế. |
| Nâng cấp | Phiên bản cũ đang hoạt động | Cài phiên bản mới cùng package identity | Binary được cập nhật, dữ liệu và cấu hình cần giữ được bảo toàn, migration hoàn tất. |
| Gỡ cài đặt | Ứng dụng đã cài | Gỡ package hoặc xóa app theo kênh phân phối | Thành phần thuộc ứng dụng được xử lý đúng chính sách; dữ liệu người dùng được giữ hoặc xóa theo lựa chọn đã công bố. |

Nên kiểm thử thêm hai luồng liên quan:

- **Cài lại:** gỡ phiên bản hiện tại rồi cài lại cùng phiên bản hoặc phiên bản mới.
- **Khôi phục sau lỗi:** cài đặt hoặc nâng cấp thất bại giữa chừng; máy phải ở trạng thái có thể sửa chữa, cài lại hoặc tiếp tục nâng cấp.

Không gộp tất cả vào một test “installer chạy xong”. Mỗi luồng có tiền điều kiện, thao tác, trạng thái kỳ vọng và cách thu thập bằng chứng riêng.

## 2. Xác định phạm vi và chính sách dữ liệu trước khi viết test

Trước khi tạo test case, xác định installer quản lý những gì:

| Nhóm | Ví dụ | Chính sách cần xác định |
|---|---|---|
| Binary ứng dụng | Launcher, JAR, runtime image, native library | Phải được cập nhật và gỡ theo package. |
| File cấu hình hệ thống | File trong thư mục cài đặt hoặc thư mục cấu hình dùng chung | Giữ, hợp nhất hay tạo lại khi nâng cấp; xử lý ra sao khi gỡ. |
| Cấu hình người dùng | Preferences, file cấu hình trong home/profile | Có được giữ khi gỡ không; người dùng có thể xuất hoặc xóa bằng lựa chọn riêng không. |
| Dữ liệu nghiệp vụ | Database, project, tài liệu, cache có giá trị | Thông thường cần bảo toàn qua nâng cấp và gỡ ứng dụng trừ khi người dùng yêu cầu xóa. |
| Thành phần tích hợp hệ điều hành | Shortcut, file association, service, scheduled task, registry, desktop entry | Phải được tạo đúng, cập nhật và dọn đúng khi gỡ. |
| Log và file tạm | Log chẩn đoán, lock file, cache | Có thể giữ log cần thiết để hỗ trợ; xóa file tạm và file không còn dùng. |

Phân loại rõ file do package sở hữu và file do ứng dụng tạo trong lúc chạy. Không để uninstall xóa toàn bộ thư mục dữ liệu chỉ vì thư mục đó nằm gần thư mục cài đặt.

Ví dụ phân vùng:

~~~text
Application binaries:
  Windows: C:\Program Files\InventoryDesk\
  macOS:   /Applications/InventoryDesk.app
  Linux:   /opt/inventory-desk/

Per-user data:
  Windows: %APPDATA%\Example\InventoryDesk\
  macOS:   ~/Library/Application Support/InventoryDesk/
  Linux:   ~/.local/share/inventory-desk/

Per-user configuration:
  Windows: %APPDATA%\Example\InventoryDesk\
  macOS:   ~/Library/Preferences/ hoặc ~/Library/Application Support/
  Linux:   ~/.config/inventory-desk/
~~~

Đây là ví dụ về cách phân vùng dữ liệu, không phải đường dẫn bắt buộc của jpackage. Chọn vị trí theo quy ước của từng nền tảng và ghi rõ chính sách giữ/xóa.

## 3. Lập ma trận kiểm thử dùng chung

Ma trận tối thiểu nên có các tình huống sau:

| ID | Tiền điều kiện | Thao tác | Kết quả cần xác nhận |
|---|---|---|---|
| L01 | Máy sạch | Cài mới | Cài thành công, launcher chạy được, metadata đúng. |
| L02 | Ứng dụng đã cài cùng version | Chạy installer lại | Kết quả đúng chính sách: repair, reinstall hoặc báo đã cài; không tạo bản cài trùng ngoài ý muốn. |
| L03 | Phiên bản N-1 đã cài | Cài phiên bản N | Nâng cấp thành công, package identity đúng, dữ liệu được giữ. |
| L04 | Phiên bản cũ nhất còn hỗ trợ | Nâng thẳng lên N | Migration từ trạng thái cũ nhất vẫn hoạt động. |
| L05 | Phiên bản N đã cài | Thử cài phiên bản cũ hơn | Downgrade bị từ chối hoặc thực hiện theo quy trình rollback có kiểm soát. |
| L06 | Đang nâng cấp | Gây lỗi trong môi trường thử nghiệm | Package manager báo lỗi; ứng dụng và dữ liệu ở trạng thái phục hồi được. |
| L07 | Phiên bản N mới cài | Gỡ ứng dụng | Binary và tích hợp được dọn đúng; dữ liệu theo chính sách. |
| L08 | Đã nâng từ N-1 lên N | Gỡ ứng dụng | Không để lại binary cũ, service hoặc registration lỗi thời. |
| L09 | Đã gỡ ứng dụng | Cài lại | Ứng dụng hoạt động; dữ liệu được khôi phục hoặc khởi tạo theo chính sách. |
| L10 | Có cấu hình người dùng đã chỉnh | Nâng cấp rồi gỡ | Cấu hình quan trọng không bị ghi đè hoặc xóa ngoài ý muốn. |
| L11 | Ứng dụng đang chạy | Nâng cấp hoặc gỡ | Installer xử lý tiến trình và file đang khóa theo thiết kế. |
| L12 | Có nhiều user hoặc nhiều phiên bản | Cài/gỡ trong từng context | Không xóa nhầm dữ liệu hoặc registration của user/phiên bản khác. |

Với sản phẩm có service, database, auto-start hoặc file association, thêm test riêng cho từng thành phần.

## 4. Chuẩn bị dữ liệu kiểm thử có thể lặp lại

Một test nâng cấp chỉ có ý nghĩa khi phiên bản cũ đã có trạng thái giống máy người dùng thật. Chuẩn bị ít nhất:

1. Máy ảo hoặc snapshot hệ điều hành sạch.
2. Installer của phiên bản cũ còn được hỗ trợ.
3. Installer của phiên bản mới.
4. Dữ liệu mẫu do phiên bản cũ tạo ra.
5. File cấu hình đã được người dùng sửa thủ công.
6. Một file log, cache và file tạm để kiểm tra chính sách dọn dẹp.
7. Tài khoản thường và tài khoản có quyền quản trị nếu installer hỗ trợ cả hai.
8. Ghi lại package ID, version, đường dẫn cài đặt, service và shortcut trước test.

Ví dụ dữ liệu kiểm thử:

~~~text
test-data/
  user-config/
    preferences.json
  business-data/
    inventory.db
    sample-project.inv
  local-state/
    last-opened.txt
  expected/
    preferences.sha256
    inventory.sha256
~~~

Checksum có thể giúp xác nhận file dữ liệu không bị thay đổi ngoài dự kiến. Với database, kiểm tra cả tính nhất quán logic bằng ứng dụng hoặc công cụ database; checksum đơn thuần không chứng minh migration đúng.

Mỗi test phải bắt đầu từ snapshot hoặc script setup có thể lặp lại. Không dùng lại máy đã trải qua nhiều lần cài/gỡ mà không biết rõ trạng thái package manager.

## 5. Kiểm thử cài mới

### Tiền điều kiện

- Package chưa được cài.
- Không còn package receipt, registry entry hoặc service cũ thuộc lần cài trước.
- Không có thư mục cài đặt sót lại làm che lỗi.
- Dùng tài khoản và quyền phù hợp với kịch bản phát hành.

### Các bước

1. Cài package theo đúng cách người dùng sẽ thực hiện.
2. Ghi nhận exit code và log installer.
3. Kiểm tra package manager nhận diện đúng tên và version.
4. Kiểm tra file được cài đúng vị trí và quyền.
5. Mở ứng dụng từ shortcut/menu và từ launcher nếu có.
6. Xác nhận runtime đi kèm hoạt động đúng.
7. Kiểm tra file association, service, scheduled task và auto-start nếu sản phẩm có dùng.
8. Tạo dữ liệu mẫu và khởi động lại ứng dụng.
9. Xác nhận dữ liệu vẫn còn sau khi đóng/mở ứng dụng.

### Kết quả mong đợi

- Không thiếu file và không tạo file ngoài phạm vi đã thiết kế.
- Không ghi vào thư mục hệ thống hoặc home của user khác.
- Launcher chạy được mà không cần JDK bên ngoài nếu package được thiết kế self-contained.
- Package metadata, shortcut, icon và file association chính xác.
- Log không chứa mật khẩu, token hoặc dữ liệu nhạy cảm.
- Lần chạy đầu không yêu cầu quyền quản trị nếu chức năng không cần quyền đó.

## 6. Kiểm thử nâng cấp

Nâng cấp phải kiểm tra đồng thời package identity, binary, cấu hình và dữ liệu. Không chỉ xác nhận version hiển thị đã đổi.

### Các trường hợp nâng cấp

- N-1 lên N: đường nâng cấp thông thường.
- Phiên bản cũ nhất còn hỗ trợ lên N: phát hiện migration tích lũy.
- Bỏ qua nhiều bản trung gian: kiểm tra đường nâng cấp trực tiếp nếu sản phẩm công bố hỗ trợ.
- Cài lại cùng version: kiểm tra hành vi repair/reinstall.
- Nâng cấp khi ứng dụng đang chạy: kiểm tra xử lý process và file lock.
- Nâng cấp khi user đã chỉnh cấu hình: xác nhận không ghi đè dữ liệu cá nhân.
- Nâng cấp với service đang hoạt động: xác nhận stop/start và health check.

### Các điểm cần xác minh

1. Package manager nhận đây là đúng sản phẩm đang cài.
2. Version mới được ghi nhận.
3. Binary và runtime cũ được thay thế đúng.
4. File không còn dùng từ phiên bản trước được dọn nếu chính sách yêu cầu.
5. Cấu hình người dùng được giữ hoặc migrate có kiểm soát.
6. Database migration hoàn tất và có thể đọc/ghi bằng phiên bản mới.
7. Shortcut, menu entry, service và file association trỏ tới phiên bản mới.
8. Không còn process cũ hoặc file bị khóa sau khi installer kết thúc.
9. Log nâng cấp thể hiện bước thành công và lỗi có thể chẩn đoán.

### Kiểm thử migration dữ liệu

Nếu schema hoặc format dữ liệu thay đổi:

- Tạo dữ liệu bằng phiên bản cũ, không tạo trực tiếp bằng phiên bản mới.
- Chạy nâng cấp và xác nhận dữ liệu cũ đọc được.
- Thử các trường hợp dữ liệu rỗng, lớn, thiếu trường tùy chọn và có giá trị biên.
- Chạy lại bước migration nếu quy trình có thể được gọi lại; không được nhân đôi dữ liệu hoặc làm hỏng trạng thái.
- Kiểm tra backup trước khi migration không tương thích.
- Xác nhận phiên bản mới ghi dữ liệu mà phiên bản cũ không thể đọc; nếu có, không cho downgrade tự động mà không có backup/restore.

Migration cần có version marker rõ ràng. Không chỉ kiểm tra “cột đã tồn tại” nếu nhiều bước chuyển đổi có thứ tự phụ thuộc nhau.

## 7. Kiểm thử gỡ cài đặt

Gỡ cài đặt cần kiểm tra cả thành phần package quản lý và dữ liệu mà ứng dụng tạo ra.

### Các bước

1. Đóng ứng dụng và service theo đúng quy trình.
2. Gỡ bằng giao diện hoặc package manager mà người dùng được hướng dẫn.
3. Ghi nhận exit code và log.
4. Kiểm tra launcher, binary, runtime và shortcut đã được dọn.
5. Kiểm tra service, scheduled task, registry, file association hoặc desktop entry đã được xử lý.
6. Kiểm tra package manager không còn trạng thái package đã cài.
7. Kiểm tra dữ liệu người dùng theo chính sách đã công bố.
8. Khởi động lại máy hoặc đăng xuất/đăng nhập nếu thành phần hệ thống yêu cầu.
9. Xác nhận không có process hoặc auto-start entry cố khởi chạy đường dẫn đã bị xóa.

Không coi việc xóa thư mục cài đặt là đủ. Có thể còn service, scheduled task, file association, package receipt, shortcut hoặc biến môi trường.

### Dữ liệu nào nên được giữ?

Đối với ứng dụng desktop, gỡ binary thường không đồng nghĩa xóa dữ liệu người dùng. Nếu sản phẩm có lựa chọn “Remove user data”, hãy kiểm thử lựa chọn này riêng, yêu cầu xác nhận rõ và mô tả chính xác phạm vi xóa.

Nếu ứng dụng là server hoặc agent, chính sách có thể khác. Cần ghi rõ dữ liệu nào được giữ để cài lại, dữ liệu nào thuộc hệ thống và dữ liệu nào bị xóa khi administrator chọn purge.

## 8. Windows MSI/EXE: kiểm thử cài mới, nâng cấp và gỡ

Windows Installer có các khái niệm ProductCode, UpgradeCode, ProductVersion và installation context. jpackage cung cấp **--win-upgrade-uuid** để liên kết các bản MSI thuộc cùng họ nâng cấp.

### Cài mới

~~~powershell
msiexec /i .\InventoryDesk-2.4.1.msi /qn /L*v .\install.log
~~~

Kiểm tra package đã đăng ký, shortcut, thư mục cài và ứng dụng chạy được. Có thể đọc ProductName, ProductVersion và ProductCode bằng công cụ MSI database như Orca.

### Nâng cấp

Với major upgrade, MSI mới thường có ProductCode mới và giữ UpgradeCode của họ sản phẩm. Upgrade table cùng các action như FindRelatedProducts và RemoveExistingProducts xác định phiên bản cũ nào được thay thế. jpackage dùng **--win-upgrade-uuid** để gán UpgradeCode; vẫn phải kiểm tra MSI đầu ra và thử nâng cấp thật.

Ví dụ cài bản mới:

~~~powershell
msiexec /i .\InventoryDesk-2.4.2.msi /qn /L*v .\upgrade.log
~~~

Kịch bản kiểm thử:

- Cài bản 2.4.1, tạo dữ liệu và cấu hình mẫu.
- Cài bản 2.4.2 với cùng Upgrade UUID.
- Xác nhận bản cũ được nâng cấp theo thiết kế, không xuất hiện hai bản cài ngoài ý muốn.
- Xác nhận dữ liệu người dùng và installation context được giữ.
- Kiểm tra shortcut và uninstall entry trỏ tới bản mới.

Windows Installer không nâng cấp major upgrade xuyên installation context: bản cài per-user cần được nâng cấp trong per-user context; bản per-machine cần được nâng cấp trong per-machine context. Kiểm thử cả hai context nếu sản phẩm hỗ trợ.

### Gỡ cài đặt

Có thể gỡ theo ProductCode:

~~~powershell
msiexec /x "{PRODUCT-CODE-GUID}" /qn /L*v .\uninstall.log
~~~

Thay GUID bằng ProductCode đọc từ MSI thực tế. Kiểm tra package đã biến mất khỏi danh sách cài đặt, binary và shortcut đã được dọn, service và registration đã được xử lý. Dữ liệu người dùng cần được giữ hoặc xóa theo chính sách.

### Rollback và lỗi cài đặt

Windows Installer bật rollback mặc định. Khi cài đặt thất bại, installer có thể phục hồi file và trạng thái đã thay đổi. Custom action muốn tham gia rollback phải có hành động rollback được thiết kế tương ứng.

Trong môi trường test:

- Tạo tình huống lỗi có kiểm soát ở một bước cài đặt.
- Xác nhận rollback log và trạng thái package.
- Kiểm tra bản cũ vẫn chạy sau khi nâng cấp thất bại.
- Thử cài lại để xác nhận máy không mắc kẹt ở trạng thái nửa cài.

Không tắt rollback chỉ để làm installer chạy nhanh hơn. Không dùng máy production để tạo lỗi giả lập.

## 9. macOS PKG, DMG và app bundle: kiểm thử đúng kênh phân phối

macOS có các hình thức phân phối khác nhau:

- **PKG:** cài thông qua Installer và thường tạo package receipt.
- **DMG chứa app bundle:** người dùng mở disk image rồi kéo app vào Applications; thao tác này không tương đương cài PKG.
- **App image:** thư mục app bundle được tạo bằng jpackage; khi copy thủ công, hệ thống không có package manager receipt như PKG.

### Cài mới PKG

~~~bash
sudo installer -pkg InventoryDesk-2.4.1.pkg -target /
~~~

Kiểm tra package receipt:

~~~bash
pkgutil --pkgs | grep -i inventory
pkgutil --pkg-info com.example.inventory.pkg
pkgutil --files com.example.inventory.pkg
~~~

Dùng package identifier thực tế của installer. Kiểm tra app bundle, launcher, quyền file và ứng dụng khởi chạy được.

### Nâng cấp PKG

~~~bash
sudo installer -pkg InventoryDesk-2.4.2.pkg -target /
~~~

Xác nhận:

- Bundle identifier của app vẫn đúng.
- Version trong Info.plist được cập nhật.
- Package receipt có version/install time phù hợp.
- App bundle không còn file cũ không được sử dụng.
- Dữ liệu trong Application Support và home của user được bảo toàn.
- App đã ký và notarize vẫn xác minh được sau khi cài.

Không giả định package receipt là trình quản lý nâng cấp đầy đủ. Receipt ghi nhận package và file được installer quản lý; hãy kiểm tra nội dung thực tế sau khi nâng cấp.

### Gỡ cài đặt PKG

macOS không cung cấp một lệnh phổ quát để gỡ mọi PKG của bên thứ ba chỉ dựa vào package ID. Ưu tiên uninstaller chính thức của nhà phát hành nếu có. Nếu không, sản phẩm cần xác định rõ danh sách file thuộc ứng dụng và cung cấp hướng dẫn gỡ an toàn.

Có thể dùng pkgutil để kiểm tra package receipt và file được ghi nhận:

~~~bash
pkgutil --pkg-info com.example.inventory.pkg
pkgutil --files com.example.inventory.pkg
~~~

**pkgutil --forget** chỉ xóa receipt khỏi cơ sở dữ liệu Installer; nó không xóa file đã cài. Không dùng lệnh này như một lệnh uninstall.

### Gỡ app bundle từ DMG/app-image

Với app được kéo vào Applications, test theo luồng người dùng:

1. Thoát ứng dụng.
2. Xóa app bundle theo hướng dẫn sản phẩm.
3. Kiểm tra login item, helper, launch agent/daemon và file association nếu app đã tạo.
4. Kiểm tra dữ liệu người dùng theo chính sách.
5. Mở lại file tài liệu hoặc shortcut cũ để bảo đảm không còn trỏ tới app đã xóa.

Việc xóa app bundle không tự động xóa mọi dữ liệu hỗ trợ trong Library. Phải phân biệt dữ liệu người dùng với file do installer tạo.

## 10. Debian/Ubuntu DEB: remove và purge là hai test khác nhau

DEB được quản lý bởi dpkg và thường được cài qua APT. Dùng APT để cài file cục bộ nếu cần giải quyết dependency:

~~~bash
sudo apt install ./inventory-desk_2.4.1-1_amd64.deb
~~~

### Cài mới và nâng cấp

~~~bash
sudo apt install ./inventory-desk_2.4.2-1_amd64.deb
dpkg-query -W -f='${Package} ${Version} ${Status}\n' inventory-desk
~~~

Kiểm tra version, trạng thái Installed, file được cài, desktop entry và dependency. Với maintainer scripts, Debian có thể gọi scripts của phiên bản cũ và mới trong các giai đoạn upgrade; script phải xử lý đúng đối số và có tính idempotent.

### Remove

~~~bash
sudo apt remove inventory-desk
~~~

Remove gỡ các file thuộc package nhưng giữ lại conffiles và một số dữ liệu cấu hình theo quy tắc dpkg. Kiểm tra package ở trạng thái đã remove nhưng còn config-files nếu có.

### Purge

~~~bash
sudo apt purge inventory-desk
~~~

Purge gỡ package và các conffiles mà dpkg quản lý, đồng thời gọi postrm với hành động purge. Dữ liệu trong home của người dùng hoặc file được ứng dụng tự tạo ngoài danh sách package không tự động bị dpkg xóa; nếu muốn xóa, phải có chính sách và thao tác riêng.

Kiểm tra trạng thái:

~~~bash
dpkg-query -W -f='${Package} ${Status}\n' inventory-desk
dpkg -L inventory-desk
~~~

Sau purge, truy vấn package có thể báo không còn package tương ứng; kiểm tra bằng lệnh phù hợp và exit code, không chỉ tìm dòng text trong output.

### Kiểm thử maintainer scripts

Nếu DEB có preinst, postinst, prerm hoặc postrm:

- Kiểm tra luồng install, upgrade, remove, purge và failed-upgrade.
- Script phải idempotent vì dpkg có thể gọi lại khi phục hồi lỗi.
- Không ghi đè cấu hình người dùng một cách âm thầm.
- Xử lý đúng trường hợp dependency chưa được cấu hình đầy đủ.
- Không giả định mọi lệnh ngoài đều sẵn sàng trong postrm.
- Kiểm tra exit code và trạng thái package sau khi script lỗi.

Có thể xem script trong package đã cài bằng:

~~~bash
dpkg-query --control-show inventory-desk postinst
dpkg-query --control-show inventory-desk prerm
dpkg-query --control-show inventory-desk postrm
~~~

Chỉ dùng lệnh xem script khi package có các control script tương ứng. Nếu gói không có script, lệnh có thể báo không tìm thấy.

## 11. Fedora/RHEL/openSUSE RPM: kiểm thử transaction upgrade

RPM được quản lý qua package manager của bản phân phối. Trên hệ thống DNF, ưu tiên dùng DNF để giải quyết dependency:

~~~bash
sudo dnf install ./inventory-desk-2.4.1-1.x86_64.rpm
~~~

Nâng cấp bằng package mới:

~~~bash
sudo dnf upgrade ./inventory-desk-2.4.2-1.x86_64.rpm
rpm -q inventory-desk
~~~

Có thể dùng rpm -U trong môi trường test chuyên biệt:

~~~bash
sudo rpm -Uvh inventory-desk-2.4.2-1.x86_64.rpm
~~~

### Gỡ cài đặt

~~~bash
sudo dnf remove inventory-desk
~~~

Kiểm tra package đã biến mất:

~~~bash
rpm -q inventory-desk
~~~

### Kiểm thử RPM scriptlets

RPM có các scriptlet như %pre, %post, %preun và %postun. Trong transaction upgrade, RPM cài phiên bản mới và xóa phiên bản cũ như các thao tác liên quan; tham số của scriptlet có thể dùng để phân biệt install lần đầu, upgrade và removal cuối cùng.

Kiểm tra scriptlet đã đóng gói:

~~~bash
rpm -q --scripts inventory-desk
~~~

Kịch bản cần xác nhận:

- Cài mới không chạy cleanup của uninstall.
- Upgrade không xóa dữ liệu hoặc service mà phiên bản mới cần.
- Gỡ phiên bản cuối cùng mới dọn tài nguyên package-specific.
- Scriptlet có thể chạy trong môi trường transaction với dependency và file system ở trạng thái chuyển tiếp.
- Exit code lỗi được ghi nhận và không khiến transaction để lại trạng thái khó phục hồi.

RPM không cung cấp rollback toàn bộ side effect của scriptlet như một giao dịch database. Vì vậy, scriptlet phải ngắn, có thể lặp lại, kiểm tra điều kiện trước khi sửa hệ thống và không thực hiện migration dữ liệu không thể đảo ngược mà thiếu backup.

## 12. Phân biệt rollback installer và rollback dữ liệu

Rollback của package manager thường phục hồi file package hoặc trạng thái cài đặt trong phạm vi mà công cụ quản lý. Nó không tự động đảo ngược mọi thay đổi do ứng dụng thực hiện.

Ví dụ:

- Windows Installer có cơ chế rollback cho các thao tác được authoring trong MSI; custom action cần rollback action phù hợp.
- dpkg có error unwind cho nhiều bước unpack/upgrade nhưng có các điểm không thể quay lui; maintainer scripts phải xử lý các trạng thái lỗi.
- RPM scriptlet có thể tạo side effect mà transaction không tự hoàn tác.
- macOS Installer ghi receipt và cài payload; không có cơ chế chung tự khôi phục mọi dữ liệu ứng dụng sau một script tùy chỉnh lỗi.

Với database migration, dùng backup, migration có thể lặp lại và kế hoạch khôi phục riêng. Không dựa vào việc gỡ installer để đưa schema database về version trước.

## 13. Kiểm thử downgrade và tương thích dữ liệu

Downgrade cần được xem là một luồng riêng. Không mặc định cài version cũ lên version mới sẽ hoạt động.

Kiểm thử:

1. Cài phiên bản N và tạo dữ liệu bằng schema mới.
2. Thử cài N-1 theo đúng package manager.
3. Xác nhận installer từ chối downgrade nếu sản phẩm không hỗ trợ.
4. Nếu hỗ trợ downgrade, xác nhận schema và format dữ liệu tương thích.
5. Kiểm tra dữ liệu sau downgrade bằng ứng dụng cũ.
6. Nếu không tương thích, yêu cầu restore backup hoặc giữ nguyên dữ liệu để nâng cấp lại.

Với Windows MSI, kiểm tra bảng Upgrade và điều kiện chặn phiên bản mới hơn. Với DEB/RPM, so sánh version package theo thuật toán package manager. Với macOS, kiểm tra version bundle và chính sách cập nhật của sản phẩm.

## 14. Kiểm thử tiến trình đang chạy và file bị khóa

Installer có thể thất bại khi ứng dụng hoặc service đang giữ file. Cần kiểm tra:

- Nâng cấp khi cửa sổ ứng dụng đang mở.
- Gỡ khi ứng dụng đang chạy ở background.
- Service đang xử lý request.
- Có file log hoặc database đang được ghi.
- User khác đang đăng nhập và dùng ứng dụng.
- Máy bị suspend/restart trong lúc cài nếu sản phẩm có kịch bản triển khai dài.

Hành vi mong đợi phải rõ ràng: yêu cầu thoát ứng dụng, dừng service có kiểm soát, chờ tiến trình kết thúc hoặc yêu cầu restart. Không xóa binary đang được dùng theo cách khiến ứng dụng hỏng âm thầm.

## 15. Kiểm thử quyền và phạm vi cài đặt

### Windows

- Cài per-user bằng tài khoản thường.
- Cài per-machine với quyền quản trị.
- Nâng cấp trong cùng installation context.
- Thử nâng cấp chéo per-user/per-machine và xác nhận hành vi đúng chính sách.
- Đảm bảo uninstall của một user không xóa cài đặt hoặc dữ liệu của user khác.

### macOS

- Cài PKG yêu cầu admin và app bundle kéo thủ công vào Applications.
- Kiểm tra quyền sở hữu file, executable bit và Gatekeeper.
- Kiểm tra login item hoặc launch daemon có đúng phạm vi user/system.
- Không xóa file hệ thống hoặc thư mục Library dùng chung ngoài phạm vi ứng dụng.

### Linux

- Cài package hệ thống qua sudo và kiểm tra owner/group.
- Chạy ứng dụng bằng user thường.
- Gỡ package bằng package manager và kiểm tra dữ liệu home của user khác.
- Kiểm tra service systemd nếu sản phẩm có service; xác nhận trạng thái enable/disable đúng sau upgrade/remove.

## 16. Kiểm thử file association, shortcut và service

Các thành phần tích hợp hệ điều hành cần được kiểm tra ở cả ba giai đoạn:

| Thành phần | Cài mới | Nâng cấp | Gỡ |
|---|---|---|---|
| Shortcut/menu entry | Tạo đúng tên và đích | Trỏ tới launcher mới, không tạo bản trùng | Xóa entry do ứng dụng tạo |
| File association | Đăng ký extension/MIME type | Giữ association và cập nhật icon/launcher nếu cần | Gỡ đăng ký do ứng dụng sở hữu; tôn trọng lựa chọn mặc định khác |
| Service | Tạo và khởi động đúng | Restart sau khi cập nhật binary/config | Stop, disable và remove theo chính sách |
| Scheduled task/auto-start | Đăng ký đúng user/system | Không nhân đôi | Xóa entry do ứng dụng tạo |
| Environment variable/PATH | Thêm đúng phạm vi | Không nối lặp | Khôi phục đúng giá trị trước đó nếu installer sở hữu thay đổi |
| Firewall rule | Tạo rule tối thiểu nếu cần | Cập nhật rule nếu định danh thay đổi | Xóa rule của ứng dụng |

Không xóa handler mặc định hoặc shortcut của ứng dụng khác. Nếu user đã thay đổi default app, uninstall nên gỡ registration thuộc sản phẩm mà không tự gán lại một ứng dụng khác.

## 17. Kiểm thử cài đặt lặp lại và tính idempotent

Một số hệ thống quản lý thiết bị có thể gửi cùng lệnh cài nhiều lần. Vì vậy, test lặp lại rất hữu ích:

1. Chạy cài mới một lần.
2. Chạy lại cùng installer.
3. Kiểm tra không có shortcut, service hoặc registry entry trùng.
4. Kiểm tra cấu hình người dùng không bị reset.
5. Kiểm tra package manager không ghi nhận nhiều package identity ngoài dự kiến.
6. Chạy lại tác vụ migration hoặc setup nếu có và xác nhận kết quả không đổi ngoài ý muốn.

Với maintainer script hoặc RPM scriptlet, thiết kế thao tác có thể chạy lại an toàn. Tránh lệnh chỉ thêm dòng vào file cấu hình mà không kiểm tra dòng đó đã tồn tại.

## 18. Kiểm thử lỗi và phục hồi

Trong môi trường cô lập, tạo các lỗi có thể tái hiện:

- Thiếu dung lượng đĩa.
- Thiếu quyền ghi vào thư mục đích.
- File ứng dụng đang bị khóa.
- Dependency không có trong repository.
- Script cấu hình trả mã lỗi.
- Migration dữ liệu thất bại.
- Mất kết nối mạng khi package manager cần tải dependency.
- Người dùng hủy installer giữa chừng.

Sau lỗi, xác minh:

1. Exit code khác 0 hoặc thông báo lỗi đúng.
2. Log ghi rõ bước thất bại.
3. Package manager không báo ứng dụng đã cài hoàn chỉnh nếu chưa hoàn tất.
4. Phiên bản cũ còn chạy được nếu rollback được kỳ vọng.
5. Dữ liệu người dùng không bị xóa hoặc truncate.
6. Có thể chạy lại installer, repair hoặc hoàn tất cấu hình.
7. Không còn service hoặc process ở trạng thái nửa cài.

Không giả định mọi hệ package đều có rollback giống nhau. Thiết kế cách phục hồi theo khả năng thực tế của Windows Installer, dpkg, RPM và Installer.app.

## 19. Bằng chứng và lệnh kiểm tra theo nền tảng

| Nền tảng | Xác nhận package đã cài | Xác nhận version/file | Gỡ |
|---|---|---|---|
| Windows MSI | Apps/Installed apps hoặc Windows Installer product registration | MSI database, log msiexec, file version | msiexec /x ProductCode |
| macOS PKG | pkgutil --pkgs, pkgutil --pkg-info | pkgutil --files, Info.plist | Uninstaller của vendor hoặc quy trình gỡ đã thiết kế |
| Debian | dpkg-query -W | dpkg-query, dpkg -L | apt remove hoặc apt purge |
| RPM | rpm -q package-name | rpm -qi, rpm -ql, rpm -q --scripts | dnf remove hoặc rpm -e |

Các lệnh macOS:

~~~bash
pkgutil --pkgs
pkgutil --pkg-info com.example.inventory.pkg
pkgutil --files com.example.inventory.pkg
~~~

Các lệnh Debian:

~~~bash
dpkg-query -W -f='${Package} ${Version} ${Status}\n' inventory-desk
dpkg -L inventory-desk
~~~

Các lệnh RPM:

~~~bash
rpm -q inventory-desk
rpm -qi inventory-desk
rpm -ql inventory-desk
rpm -q --scripts inventory-desk
~~~

Lệnh Windows:

~~~powershell
Get-AuthenticodeSignature .\InventoryDesk.exe
Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' |
    Where-Object DisplayName -Like '*InventoryDesk*' |
    Select-Object DisplayName, DisplayVersion, UninstallString
~~~

Vị trí đăng ký uninstall có thể khác theo per-user/per-machine và kiến trúc. Dùng Windows Installer API hoặc công cụ inventory phù hợp khi cần kiểm tra chính xác; không hardcode một registry path duy nhất cho mọi context.

## 20. Mẫu test case cho một bản phát hành

| Trường | Ví dụ |
|---|---|
| Test ID | INSTALL-UPGRADE-003 |
| Mục tiêu | Nâng từ bản 2.4.1 lên 2.4.2 và giữ dữ liệu |
| Nền tảng | Ubuntu LTS, amd64 |
| Tiền điều kiện | inventory-desk 2.4.1-1 đã cài; database mẫu có 100 bản ghi |
| Thao tác | Cài inventory-desk 2.4.2-1 bằng APT |
| Kết quả package | dpkg-query báo 2.4.2-1 và trạng thái installed |
| Kết quả dữ liệu | 100 bản ghi còn nguyên; schema marker đã cập nhật |
| Kết quả ứng dụng | Launcher chạy, đọc và ghi dữ liệu được |
| Bằng chứng | Log APT, dpkg-query output, test report, checksum database |
| Kết quả | PASS/FAIL và link tới log |

Giữ test case có thể chạy lại trên snapshot. Ghi rõ version installer, OS build, architecture, user context và dữ liệu đầu vào để có thể tái hiện lỗi.

## 21. Lỗi thường gặp trong kiểm thử vòng đời

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cài mới chạy được nhưng upgrade lỗi | Chỉ test trên máy sạch | Thêm test từ N-1 và phiên bản cũ nhất còn hỗ trợ. |
| Cấu hình người dùng bị reset | Installer chép đè file cấu hình mặc định | Tách config do package sở hữu khỏi config người dùng; kiểm tra merge/migration. |
| Uninstall xóa database | Dữ liệu nằm trong thư mục bị xóa cùng binary | Phân vùng data directory và xác định chính sách giữ/xóa. |
| Debian remove vẫn còn config | Đây là hành vi bình thường với conffiles | Test remove và purge như hai trường hợp khác nhau. |
| macOS pkgutil vẫn liệt kê package sau khi xóa app | Receipt còn tồn tại hoặc chỉ bị xóa file app | Kiểm tra receipt và file riêng; nhớ --forget chỉ xóa receipt. |
| RPM upgrade xóa service/data | Scriptlet coi upgrade như uninstall cuối | Kiểm tra đối số scriptlet và chỉ cleanup khi package thực sự bị gỡ cuối cùng. |
| MSI cài song song bản cũ | UpgradeCode hoặc Upgrade table không khớp | Kiểm tra MSI metadata và test major upgrade thực tế. |
| Upgrade thất bại nhưng app không chạy | Migration hoặc script đã tạo side effect không thể đảo ngược | Backup, migration idempotent và quy trình phục hồi dữ liệu. |
| Gỡ xong vẫn có auto-start | Chưa dọn service, launch agent hoặc scheduled task | Thêm kiểm tra từng integration point sau uninstall. |
| Cài lại tạo shortcut/service trùng | Setup không idempotent | Kiểm tra trạng thái trước khi tạo và dọn đúng entry thuộc ứng dụng. |

## 22. Quy trình kiểm thử phát hành đề xuất

1. Tạo snapshot hệ điều hành sạch cho từng nền tảng và kiến trúc hỗ trợ.
2. Cài phiên bản cũ, tạo cấu hình và dữ liệu đại diện.
3. Kiểm thử nâng cấp lên phiên bản mới, gồm nâng cấp trực tiếp và nâng cấp qua phiên bản cũ nhất còn hỗ trợ.
4. Kiểm tra migration, shortcut, file association, service, quyền và package metadata.
5. Kiểm thử downgrade và lỗi cài đặt trong môi trường cô lập.
6. Gỡ ứng dụng sau cài mới và sau nâng cấp.
7. Kiểm tra remove/purge của DEB và receipt của PKG theo đúng semantics.
8. Cài lại và xác nhận dữ liệu được giữ hoặc khởi tạo theo chính sách.
9. Lặp lại các test với user thường, admin và nhiều user nếu hỗ trợ.
10. Lưu log, version, OS build, architecture, dữ liệu đầu vào và kết quả.

## 23. Cách áp dụng trong quy trình Java hiện đại

- Dùng **jpackage** tạo artifact cho từng nền tảng; chạy build và test trên OS tương ứng.
- Tách test cài mới, nâng cấp, gỡ, cài lại và phục hồi lỗi.
- Trên Windows, giữ UpgradeCode ổn định, kiểm tra ProductVersion, ProductCode và installation context.
- Trên macOS, phân biệt PKG receipt với app bundle kéo từ DMG; không dùng **pkgutil --forget** như lệnh gỡ cài đặt.
- Trên Debian, kiểm thử riêng **apt remove** và **apt purge**, đồng thời xác minh maintainer scripts và conffiles.
- Trên RPM, kiểm tra **dnf upgrade/remove**, scriptlets và hành vi khi transaction lỗi.
- Giữ dữ liệu người dùng tách khỏi binary và cấu hình mặc định; backup trước migration không tương thích.
- Kiểm thử trên snapshot sạch, ghi log và xác minh package manager sau mỗi thao tác.
- Chỉ phát hành khi nâng cấp, gỡ và cài lại đều cho kết quả đúng chính sách dữ liệu.

Một kế hoạch kiểm thử installer tốt chứng minh được ba điều: cài mới tạo đúng trạng thái, nâng cấp chuyển trạng thái mà không làm mất dữ liệu, và gỡ cài đặt dọn đúng thành phần mà không xóa nhầm dữ liệu người dùng. Cần xác minh từng nền tảng bằng package manager và công cụ hệ điều hành của nó, vì MSI, PKG, DEB và RPM có cơ chế vòng đời khác nhau.

## Tài liệu tham khảo

- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle JDK 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Microsoft Learn — Major Upgrades](https://learn.microsoft.com/en-us/windows/win32/msi/major-upgrades)
- [Microsoft Learn — Applying Major Upgrades by Installing the Product](https://learn.microsoft.com/en-us/windows/win32/msi/applying-major-upgrades-by-installing-the-product)
- [Microsoft Learn — Rollback Installation](https://learn.microsoft.com/en-us/windows/win32/msi/rollback-installation)
- [Microsoft Learn — Installation Context](https://learn.microsoft.com/en-us/windows/win32/msi/installation-context)
- [Debian Policy — Package Maintainer Scripts and Installation Procedure](https://www.debian.org/doc/debian-policy/ch-maintainerscripts)
- [Debian Manpages — dpkg](https://manpages.debian.org/unstable/dpkg/dpkg.1.en.html)
- [RPM — Scriptlets and Transaction Processing](https://rpm.org/docs/latest/manual/file_triggers.html)
- [Apple — Installing Packages](https://developer.apple.com/documentation/devicemanagement/installing-packages)
- [macOS Manual — pkgutil](https://manp.gs/mac/1/pkgutil)
