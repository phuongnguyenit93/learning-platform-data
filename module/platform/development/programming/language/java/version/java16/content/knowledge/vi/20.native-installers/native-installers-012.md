# Xử lý version, tên gói và ràng buộc của từng định dạng installer

Khi phát hành ứng dụng Java bằng **jpackage**, cùng một bản phát hành có thể được đóng gói thành MSI/EXE trên Windows, PKG/DMG trên macOS và DEB/RPM trên Linux. Mỗi hệ điều hành có quy tắc riêng cho phiên bản, tên ứng dụng, tên package và cách so sánh phiên bản khi nâng cấp.

Vì vậy, không nên lấy một chuỗi SemVer bất kỳ rồi truyền nguyên vẹn vào mọi installer. Hãy duy trì một phiên bản phát hành chuẩn của ứng dụng, sau đó ánh xạ thành giá trị hợp lệ cho từng nền tảng. Đồng thời, giữ ổn định các định danh package để hệ điều hành nhận ra bản mới là bản nâng cấp của ứng dụng đã cài.

Trong module Java 16, **jpackage** đã là công cụ đóng gói ổn định và các tùy chọn dưới đây vẫn hữu ích trong Java hiện đại. Bài này tập trung vào **--app-version**, **--name**, **--linux-package-name**, **--linux-app-release**, **--mac-package-name**, **--mac-package-identifier** và **--win-upgrade-uuid**, cùng giới hạn của Windows Installer, macOS bundle, DEB và RPM.

## 1. Phân biệt các loại tên và phiên bản

Một ứng dụng có nhiều giá trị định danh. Chúng không thay thế lẫn nhau:

| Giá trị | Vai trò | Ví dụ |
|---|---|---|
| Tên hiển thị | Tên người dùng nhìn thấy | Inventory Desk |
| Tên package | Tên package manager dùng để cài/nâng cấp/gỡ | inventory-desk |
| Phiên bản ứng dụng | Phiên bản sản phẩm do nhóm phát triển quản lý | 2.4.1 |
| Revision package | Lần đóng gói lại của cùng phiên bản ứng dụng | 1 |
| Bundle identifier | Định danh ứng dụng macOS | com.example.inventory |
| Upgrade UUID | Nhận diện họ MSI Windows qua các lần phát hành | Một GUID ổn định |
| Build number | Mã lần build cụ thể | 57 |

Các tùy chọn jpackage liên quan:

| Tùy chọn | Ý nghĩa |
|---|---|
| **--name** | Tên ứng dụng và/hoặc package. |
| **--app-version** | Phiên bản ứng dụng và/hoặc package. |
| **--linux-package-name** | Tên package Linux; mặc định lấy từ tên ứng dụng. |
| **--linux-app-release** | Trường Release của RPM hoặc Debian revision của DEB. |
| **--mac-package-name** | Tên ngắn của ứng dụng hiển thị trong menu bar macOS. |
| **--mac-package-identifier** | Bundle identifier của ứng dụng macOS. |
| **--win-upgrade-uuid** | UUID nhận diện các phiên bản MSI thuộc cùng một họ nâng cấp. |

Ví dụ, Inventory Desk có thể dùng tên hiển thị Inventory Desk, package name inventory-desk, phiên bản 2.4.1 và bundle identifier com.example.inventory. Khi phát hành 2.4.2, giữ nguyên tên package và bundle identifier; chỉ tăng version theo quy tắc của nền tảng.

## 2. Thiết kế một nguồn version chuẩn

Nên quản lý một phiên bản phát hành chuẩn trong quy trình build, ví dụ:

~~~text
APP_VERSION=2.4.1
PACKAGE_REVISION=1
BUILD_NUMBER=57
~~~

Ba giá trị có mục đích khác nhau:

- APP_VERSION thay đổi khi sản phẩm có bản phát hành mới.
- PACKAGE_REVISION thay đổi khi cần đóng gói lại cùng một phiên bản ứng dụng, chẳng hạn sửa metadata, thay đổi script cài đặt hoặc build lại package.
- BUILD_NUMBER nhận diện lần build trong CI. Không phải định dạng installer nào cũng có trường riêng cho giá trị này.

Ví dụ ánh xạ một bản phát hành ổn định:

| Nền tảng | Giá trị version dùng trong package |
|---|---|
| Windows MSI/EXE | 2.4.1 |
| macOS app bundle | 2.4.1 |
| Debian DEB | 2.4.1-1 |
| RPM | 2.4.1-1 |

Không nối revision package vào **--app-version** một cách tùy tiện. Trên Linux, jpackage đã có **--linux-app-release** để tách revision khỏi version ứng dụng. Trên Windows và macOS, các trường version có giới hạn riêng và không nhất thiết chứa build number.

## 3. Dùng --app-version và --name

Ví dụ cơ bản:

~~~bash
jpackage \
  --type app-image \
  --name InventoryDesk \
  --app-version 2.4.1 \
  --input build/input \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest build/app-image
~~~

Trong đó:

- **--name** đặt tên ứng dụng dùng trong quá trình đóng gói.
- **--app-version** đặt phiên bản ứng dụng/package.
- **--dest** chỉ định thư mục đầu ra.

**--name** không phải package version. **--app-version** cũng không phải revision của package Linux. Nếu đổi **--name** tùy tiện giữa các phiên bản, tên bundle, installer hoặc shortcut có thể thay đổi và gây khó khăn khi nâng cấp. Hãy giữ tên ổn định cho cùng một sản phẩm trừ khi có kế hoạch đổi thương hiệu và chuyển đổi package rõ ràng.

Tên file đầu ra có thể chứa tên, version và kiến trúc. Đổi tên file MSI/DEB/RPM sau khi tạo không thay đổi metadata bên trong package; package manager vẫn nhận diện theo các trường đã đóng gói.

## 4. Windows: ProductVersion của MSI có giới hạn ba trường

Với MSI, Windows Installer dùng trường **ProductVersion** để so sánh phiên bản sản phẩm. Định dạng chuẩn là:

~~~text
major.minor.build
~~~

Giới hạn từng trường:

| Trường | Giá trị tối đa |
|---|---:|
| Major | 0–255 |
| Minor | 0–255 |
| Build/update | 0–65.535 |

Windows Installer chỉ sử dụng ba trường đầu. Nếu có trường thứ tư, nó bị bỏ qua khi so sánh version. jpackage trên Windows cũng kiểm tra số thành phần và giới hạn của MSI.

Vì vậy, dùng các giá trị như:

~~~text
2.4.1
2.4.2
3.0.0
~~~

Không dùng chuỗi SemVer đầy đủ có hậu tố:

~~~text
2.4.1-rc.1
2.4.1+build.57
2.4.1.57
~~~

Các chuỗi trên không phù hợp để dùng trực tiếp làm ProductVersion MSI. Trường thứ tư không giúp phân biệt build trong Windows Installer, còn chữ và dấu cộng không phải dạng ba số mà MSI yêu cầu.

Ví dụ tạo MSI:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 2.4.1 --win-upgrade-uuid 8A3B0C72-5F21-4E9D-9C16-2B7F4D0A6E31 --input build\input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

EXE do jpackage tạo cũng dựa trên công nghệ installer Windows và cần version hợp lệ theo quy trình đóng gói tương ứng. Hãy kiểm tra ProductVersion trong MSI bên trong bộ cài EXE nếu cần xác nhận metadata.

## 5. Windows: version, ProductCode và UpgradeCode

Trong MSI có nhiều mã khác nhau:

- **ProductVersion** biểu diễn phiên bản sản phẩm và tham gia phát hiện nâng cấp.
- **ProductCode** nhận diện một sản phẩm cụ thể trong Windows Installer.
- **UpgradeCode** nhận diện họ sản phẩm qua nhiều bản phát hành.

Tùy chọn **--win-upgrade-uuid** đặt UpgradeCode. Hãy giữ nguyên GUID cho các phiên bản thuộc cùng sản phẩm:

~~~powershell
$upgradeUuid = "8A3B0C72-5F21-4E9D-9C16-2B7F4D0A6E31"
jpackage --type msi --name InventoryDesk --app-version 2.4.2 --win-upgrade-uuid $upgradeUuid --input build\input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Không tạo UpgradeCode mới trong mỗi lần CI chạy. Nếu GUID đổi, MSI mới có thể không nhận diện MSI cũ là phiên bản cùng họ. ProductCode được quản lý riêng theo quy tắc Windows Installer; không dùng UpgradeCode làm ProductCode.

Version tăng không tự động bảo đảm nâng cấp hoạt động. Cần kiểm tra MSI mới có ProductVersion cao hơn theo quy tắc ba trường, cùng UpgradeCode và đúng installation context với bản cũ.

## 6. Windows: đặt tên sản phẩm ổn định

Trên Windows, **--name** là tên ứng dụng/package mà jpackage dùng để tạo installer và launcher. Nên:

- Dùng tên sản phẩm ổn định, dễ nhận biết trong Apps/Programs.
- Không gắn version vào **--name**, ví dụ tránh đổi InventoryDesk24 thành InventoryDesk25 mỗi lần phát hành nếu đó vẫn là cùng sản phẩm.
- Không đưa thông tin build hoặc kiến trúc vào tên sản phẩm hiển thị.
- Giữ UpgradeCode ổn định qua các phiên bản.
- Nếu cần kênh beta/preview độc lập, thiết kế riêng tên sản phẩm và UpgradeCode để tránh MSI preview nâng cấp hoặc gỡ bản stable ngoài ý muốn.

Ví dụ:

~~~text
Tên sản phẩm: InventoryDesk
Version: 2.4.1
UpgradeCode: giữ nguyên qua các bản 2.x
~~~

## 7. macOS: bundle name, bundle identifier và version

macOS app bundle lưu metadata trong Contents/Info.plist. Các giá trị quan trọng:

| Info.plist key | Ý nghĩa |
|---|---|
| CFBundleIdentifier | Định danh ứng dụng, thường theo reverse-DNS. |
| CFBundleName | Tên bundle ngắn. |
| CFBundleShortVersionString | Version phát hành hiển thị cho người dùng. |
| CFBundleVersion | Version của build dùng để nhận diện từng lần build. |

jpackage cung cấp:

- **--name** cho tên ứng dụng/bundle.
- **--mac-package-name** cho tên ứng dụng xuất hiện trong menu bar.
- **--mac-package-identifier** cho bundle identifier.
- **--app-version** cho version của ứng dụng/package.

Ví dụ:

~~~bash
jpackage \
  --type pkg \
  --name InventoryDesk \
  --app-version 2.4.1 \
  --mac-package-name Inventory \
  --mac-package-identifier com.example.inventory \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Theo man page JDK 16, **--mac-package-name** phải ngắn hơn 16 ký tự để phù hợp menu bar và cửa sổ thông tin ứng dụng. Chọn tên ngắn, dễ nhận biết như Inventory; giữ bundle identifier ổn định như com.example.inventory.

Không dùng bundle identifier chứa version. Ví dụ không đổi com.example.inventory.v2 mỗi khi phát hành bản 2.x nếu vẫn là cùng một ứng dụng; bundle identifier mới có thể khiến macOS và các công cụ phân phối xem đó là ứng dụng khác.

## 8. macOS: giới hạn version trong Info.plist

Apple quy định **CFBundleShortVersionString** là version phát hành gồm ba số nguyên phân cách bằng dấu chấm, ví dụ:

~~~text
2.4.1
~~~

Giá trị chỉ gồm chữ số và dấu chấm. Không dùng hậu tố như -rc1, +build57 hoặc chữ cái.

**CFBundleVersion** là version build, gồm một đến ba số nguyên phân cách bằng dấu chấm. Apple dùng giá trị này để nhận diện từng build; với ứng dụng Mac, cần tăng build version trước khi phân phối build mới.

Trong app bundle macOS mặc định do jpackage JDK 16 tạo, **--app-version** được ghi vào CFBundleShortVersionString và được dùng làm CFBundleVersion nếu giá trị phù hợp cú pháp của khóa này. Vì vậy, cấu hình mặc định dùng cùng một giá trị cho release version và build version. CLI jpackage JDK 16 không có tùy chọn riêng như --mac-build-version để truyền độc lập hai giá trị.

Điều này cần lưu ý khi gửi nhiều build của cùng một release lên App Store Connect hoặc dùng hệ thống cập nhật so sánh **CFBundleVersion**. Hãy kiểm tra Info.plist sau khi tạo app image:

~~~bash
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' build/mac/InventoryDesk.app/Contents/Info.plist
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' build/mac/InventoryDesk.app/Contents/Info.plist
~~~

Nếu quy trình phát hành yêu cầu build number độc lập với version hiển thị, hãy thiết kế bước tùy chỉnh bundle trước khi ký và notarize, hoặc dùng quy trình đóng gói phù hợp có thể quản lý hai trường riêng. Không sửa Info.plist sau khi ký vì sẽ làm chữ ký code không còn hợp lệ.

## 9. Linux: tách package name, application version và release

Trên Linux, jpackage có các giá trị riêng:

- **--name**: tên ứng dụng.
- **--linux-package-name**: tên package dùng trong DEB/RPM.
- **--app-version**: version ứng dụng/package.
- **--linux-app-release**: revision package.

Ví dụ:

~~~bash
jpackage --type deb --name InventoryDesk --linux-package-name inventory-desk --app-version 2.4.1 --linux-app-release 1 --input build/input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Kết quả có package name inventory-desk, version ứng dụng 2.4.1 và revision 1. Nên giữ **--linux-package-name** ổn định qua các bản phát hành để package manager nhận diện đây là cùng một sản phẩm.

Tên package Linux khác tên hiển thị. Inventory Desk phù hợp cho giao diện, còn inventory-desk phù hợp với package manager.

## 10. DEB: cấu trúc version và quy tắc so sánh

Debian Policy quy định version package theo dạng:

~~~text
[epoch:]upstream_version[-debian_revision]
~~~

Ba thành phần:

- **epoch**: số nguyên tùy chọn, dùng khi cần điều chỉnh thứ tự version do lịch sử đánh version thay đổi.
- **upstream_version**: version của phần mềm gốc.
- **debian_revision**: revision của package Debian.

Với jpackage:

| Trường Debian | Tùy chọn jpackage |
|---|---|
| upstream_version | **--app-version** |
| debian_revision | **--linux-app-release** |
| epoch | Không có tùy chọn riêng trong giao diện jpackage JDK 16 |

Ví dụ:

~~~bash
jpackage --type deb --name InventoryDesk --linux-package-name inventory-desk --app-version 2.4.1 --linux-app-release 1 --input build/input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Version DEB được biểu diễn như 2.4.1-1.

Khi chỉ đóng gói lại cùng version ứng dụng, tăng revision:

| Lần phát hành | Version ứng dụng | Debian revision | Version package |
|---|---|---|---|
| Lần đầu | 2.4.1 | 1 | 2.4.1-1 |
| Sửa cách đóng gói | 2.4.1 | 2 | 2.4.1-2 |
| Ứng dụng phát hành mới | 2.4.2 | 1 | 2.4.2-1 |

Theo quy ước Debian, revision thường quay về 1 khi upstream version tăng. Không tăng revision để thay thế version ứng dụng khi có thay đổi phần mềm thực sự.

## 11. DEB: ký tự hợp lệ và prerelease

Tên package Debian phải dùng chữ thường a-z, chữ số 0-9, dấu cộng, dấu trừ và dấu chấm; tên có ít nhất hai ký tự và bắt đầu bằng ký tự chữ hoặc số.

Trong version:

- upstream_version bắt đầu bằng chữ số và có thể chứa chữ số, chữ cái, dấu chấm, dấu cộng, dấu trừ và dấu ngã. Nếu không có debian_revision, upstream_version không được chứa dấu gạch ngang.
- debian_revision có thể chứa chữ số, chữ cái, dấu cộng, dấu chấm và dấu ngã; không dùng dấu gạch ngang trong revision.
- Debian dùng thuật toán so sánh version riêng, không so sánh chuỗi đơn giản theo thứ tự từ điển.

Ký tự dấu ngã được sắp xếp trước phần còn lại, nên hữu ích cho bản prerelease:

~~~text
2.4.1~rc1-1
2.4.1~rc2-1
2.4.1-1
~~~

Thứ tự trên đặt các bản RC trước bản stable 2.4.1. Với jpackage, có thể dùng version upstream phù hợp và revision riêng:

~~~bash
jpackage --type deb --name InventoryDesk --linux-package-name inventory-desk --app-version '2.4.1~rc1' --linux-app-release 1 --input build/input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Trước khi phát hành, kiểm tra Version thực tế bằng dpkg-deb -f. Không tự chèn epoch hoặc revision vào một chuỗi **--app-version** rồi giả định jpackage sẽ phân tích đúng như mong muốn.

## 12. RPM: cấu trúc EVR

RPM so sánh package theo **EVR**:

~~~text
[epoch:]version-release
~~~

Trong đó:

- **Epoch** là số nguyên ưu tiên cao nhất; thường bỏ qua và chỉ dùng khi thật sự cần sửa thứ tự nâng cấp.
- **Version** là version của phần mềm.
- **Release** phân biệt các lần đóng gói lại của cùng version.

Với jpackage:

| Trường RPM | Tùy chọn jpackage |
|---|---|
| Version | **--app-version** |
| Release | **--linux-app-release** |
| Epoch | Không có tùy chọn riêng trong giao diện jpackage JDK 16 |

Ví dụ:

~~~bash
jpackage --type rpm --name InventoryDesk --linux-package-name inventory-desk --app-version 2.4.1 --linux-app-release 1 --input build/input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Package có Version 2.4.1 và Release 1, thường được hiển thị dạng 2.4.1-1.

Quy tắc phát hành thông dụng:

1. Bắt đầu Release từ 1 cho một version mới.
2. Tăng Release khi đóng gói lại cùng Version.
3. Đặt Release về 1 khi Version ứng dụng tăng.
4. Chỉ dùng Epoch nếu thay đổi quy tắc version khiến RPM không thể nhận diện bản mới theo thứ tự đúng.

## 13. RPM: ký tự hợp lệ và prerelease

Tên RPM không được chứa khoảng trắng; dấu gạch ngang được phép trong Name. Với Version và Release, RPM dùng các ký tự ASCII chữ/số và các dấu phân đoạn như dấu chấm, gạch dưới, dấu cộng, dấu ngã và dấu mũ. Không dùng dấu gạch ngang trong Version hoặc Release vì RPM dùng dấu này phân cách các thành phần tên file và EVR.

Ví dụ version prerelease:

~~~text
2.4.1~rc1-1
2.4.1~rc2-1
2.4.1-1
~~~

RPM hiểu dấu ngã là dấu chỉ phiên bản thấp hơn bản phát hành chính thức tương ứng. Với jpackage:

~~~bash
jpackage --type rpm --name InventoryDesk --linux-package-name inventory-desk --app-version '2.4.1~rc1' --linux-app-release 1 --input build/input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Không dùng dấu gạch ngang trong giá trị **--app-version** cho RPM. Nếu hệ thống phát hành yêu cầu Epoch, cần workflow RPM có thể kiểm soát trường Epoch thay vì giả định jpackage có tùy chọn tương ứng.

## 14. So sánh version không phải so sánh chuỗi

Các package manager dùng thuật toán riêng để xác định package nào mới hơn. Ví dụ:

~~~text
2.10.0
2.9.0
~~~

Theo so sánh version dạng số, 2.10.0 mới hơn 2.9.0, dù nếu so sánh chuỗi ký tự thì ký tự 1 đứng trước 9.

Debian so sánh theo epoch, upstream version và Debian revision. RPM so sánh theo epoch, version và release. Windows Installer so sánh ba trường ProductVersion. macOS sử dụng metadata bundle và chính sách phân phối/cập nhật tương ứng.

Vì vậy:

- Không dùng phép so sánh chuỗi đơn giản trong script release.
- Kiểm tra bằng package manager hoặc công cụ so sánh version của nền tảng.
- Thử nâng cấp từ package cũ sang package mới trên môi trường sạch.
- Không dùng version thứ tư của MSI để phân biệt build.
- Không dùng revision package Linux thay cho version ứng dụng.

## 15. Đặt tên và định danh riêng cho từng nền tảng

| Nền tảng | Tên/định danh nên giữ ổn định | Version cần tăng |
|---|---|---|
| Windows MSI/EXE | **--name**, **--win-upgrade-uuid** | **--app-version** theo ProductVersion ba trường |
| macOS PKG/DMG | **--name**, **--mac-package-identifier** | **--app-version** hợp lệ cho Info.plist |
| Debian DEB | **--linux-package-name** | **--app-version**; tăng **--linux-app-release** khi đóng gói lại |
| RPM | **--linux-package-name** | **--app-version**; tăng **--linux-app-release** khi đóng gói lại |

Một số lưu ý:

- Windows: giữ Upgrade UUID ổn định cho cùng họ sản phẩm; nếu tách beta và stable thành hai dòng riêng, dùng UUID riêng.
- macOS: bundle identifier là định danh ứng dụng, không phải tên file PKG; giữ nguyên qua các bản cập nhật.
- Debian/RPM: package name là khóa nhận diện của package manager; đổi tên package có thể tạo package mới thay vì nâng cấp package cũ.
- Tên file installer chỉ phục vụ phân phối và lưu trữ; không thay thế metadata nội bộ.

## 16. Ví dụ ánh xạ cùng một release sang bốn package

Giả sử phiên bản ứng dụng chuẩn là 2.4.1, revision package là 1.

Windows MSI:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 2.4.1 --win-upgrade-uuid 8A3B0C72-5F21-4E9D-9C16-2B7F4D0A6E31 --input build\input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

macOS PKG:

~~~bash
jpackage --type pkg --name InventoryDesk --app-version 2.4.1 --mac-package-name Inventory --mac-package-identifier com.example.inventory --input build/libs --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Debian DEB:

~~~bash
jpackage --type deb --name InventoryDesk --linux-package-name inventory-desk --app-version 2.4.1 --linux-app-release 1 --input build/input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

RPM:

~~~bash
jpackage --type rpm --name InventoryDesk --linux-package-name inventory-desk --app-version 2.4.1 --linux-app-release 1 --input build/input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Các lệnh cần chạy trên đúng hệ điều hành và toolchain của package tương ứng. Ví dụ Windows MSI không được tạo từ runner Linux; macOS PKG/DMG cần runner macOS.

## 17. Kiểm tra metadata sau khi tạo package

Không chỉ nhìn tên file đầu ra. Hãy đọc metadata thực tế bên trong artifact.

### Windows MSI

Mở MSI bằng Orca hoặc công cụ đọc MSI database và kiểm tra bảng Property:

| Property | Giá trị cần kiểm tra |
|---|---|
| ProductName | Tên sản phẩm dự kiến. |
| ProductVersion | Version ba trường hợp lệ. |
| UpgradeCode | GUID ổn định của họ sản phẩm. |
| ProductCode | Mã sản phẩm của package cụ thể. |

Nếu tạo EXE, kiểm tra MSI được đóng gói bên trong hoặc metadata installer tương ứng.

### macOS

Kiểm tra Info.plist:

~~~bash
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' InventoryDesk.app/Contents/Info.plist
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' InventoryDesk.app/Contents/Info.plist
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' InventoryDesk.app/Contents/Info.plist
~~~

Kiểm tra CFBundleIdentifier, version hiển thị và build version có giá trị đúng theo chính sách phát hành.

### Debian DEB

~~~bash
dpkg-deb -f dist/inventory-desk_2.4.1-1_amd64.deb Package Version Architecture
~~~

### RPM

~~~bash
rpm -qp --qf '%{NAME}\n%{EPOCH}:%{VERSION}-%{RELEASE}\n%{ARCH}\n' dist/inventory-desk-2.4.1-1.x86_64.rpm
~~~

Tên file và kiến trúc trong ví dụ có thể khác theo môi trường build. Dùng đúng đường dẫn artifact thực tế.

## 18. Nâng cấp và đổi tên package

Nâng cấp thành công cần giữ các định danh mà package manager sử dụng:

- Windows: giữ UpgradeCode và tăng ProductVersion đúng quy tắc MSI.
- macOS: giữ bundle identifier; tăng version theo metadata bundle và hệ thống cập nhật đang dùng.
- Debian: giữ package name; version package mới phải được dpkg coi là lớn hơn.
- RPM: giữ Name; EVR mới phải lớn hơn EVR đang cài.

Không đổi package name chỉ để phản ánh version. Ví dụ, tránh tạo inventory-desk-2 chỉ vì ứng dụng chuyển từ 1.x lên 2.x nếu đây vẫn là cùng một sản phẩm. Đổi package name có thể khiến package manager cài song song hai gói và không tự nâng cấp gói cũ.

Nếu cần đổi tên sản phẩm hoặc package identity, lập kế hoạch chuyển đổi:

1. Xác định package cũ và package mới.
2. Quyết định package mới có thay thế package cũ hay cài song song.
3. Chuyển dữ liệu và cấu hình người dùng nếu vị trí thay đổi.
4. Thiết lập quan hệ upgrade/obsoletes phù hợp với package manager.
5. Kiểm thử nâng cấp từ các version cũ đang được hỗ trợ.
6. Công bố hướng dẫn chuyển đổi nếu người dùng cần thao tác.

## 19. Kênh stable, beta và prerelease

Không phải định dạng installer nào cũng hỗ trợ cùng một chuỗi version:

| Kênh | Debian | RPM | Windows MSI | macOS bundle |
|---|---|---|---|---|
| Stable | 2.4.1-1 | 2.4.1-1 | 2.4.1 | 2.4.1 |
| RC | 2.4.1~rc1-1 | 2.4.1~rc1-1 | Dùng version số theo quy ước riêng | Dùng version số theo quy ước riêng |
| Đóng gói lại cùng release | Tăng Debian revision | Tăng Release | Tăng ProductVersion nếu cần MSI update hợp lệ | Tăng build/version theo chính sách phân phối |

Với Windows và macOS, không nối -rc1 hoặc +build.57 vào version mà nền tảng yêu cầu chỉ có số. Nếu cần cài beta song song với stable, nên tách định danh sản phẩm hoặc bundle identifier và UpgradeCode cho kênh preview. Điều này tránh bản beta được package manager coi là bản nâng cấp của stable hoặc ngược lại.

Trên Linux, ký tự dấu ngã thường phù hợp để đặt prerelease trước bản stable trong thuật toán so sánh Debian và RPM. Luôn xác minh thứ tự bằng công cụ của bản phân phối mục tiêu.

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jpackage từ chối version Windows | Version có chữ, dấu cộng, quá ba trường hoặc vượt giới hạn MSI | Dùng ba trường số major.minor.build và kiểm tra giới hạn từng trường. |
| MSI không nhận build thứ tư | Windows Installer bỏ qua trường version thứ tư | Không dùng trường thứ tư để nhận diện update. |
| MSI mới cài song song bản cũ | UpgradeCode thay đổi hoặc ProductVersion không được coi là mới hơn | Giữ Upgrade UUID và kiểm tra ProductVersion. |
| macOS không chấp nhận version | Version có chữ hoặc nhiều hơn ba phần | Dùng version số phân cách bằng dấu chấm. |
| App Store Connect từ chối build mới | CFBundleVersion không tăng hoặc metadata không khớp | Kiểm tra Info.plist và chính sách build number trước khi ký/upload. |
| DEB không được coi là bản mới | Debian revision hoặc upstream version không tăng theo quy tắc dpkg | Kiểm tra Version bằng dpkg-deb -f và so sánh theo Debian Policy. |
| RPM không nâng cấp | Version/Release không tăng theo EVR hoặc dùng ký tự không hợp lệ | Kiểm tra NEVRA và so sánh bằng RPM tooling. |
| DEB/RPM cài thành package khác | **--linux-package-name** bị đổi | Giữ package name ổn định hoặc tạo migration có chủ đích. |
| Prerelease được coi là mới hơn stable ngoài ý muốn | Dùng hậu tố không đúng thuật toán package manager | Dùng dấu ngã trên Debian/RPM và kiểm thử thứ tự. |
| Tên menu macOS bị cắt hoặc cảnh báo | **--mac-package-name** quá dài | Dùng tên ngắn theo giới hạn jpackage JDK 16. |
| File installer được đổi tên nhưng package metadata vẫn cũ | Nhầm tên file với tên package | Kiểm tra metadata bên trong bằng Orca, dpkg-deb hoặc rpm. |

## 21. Quy trình phát hành đề xuất

1. Chọn tên sản phẩm ổn định và package name riêng cho Linux.
2. Chọn bundle identifier ổn định cho macOS.
3. Tạo Upgrade UUID cố định cho họ MSI Windows.
4. Quản lý một version ứng dụng chuẩn và package revision riêng.
5. Ánh xạ version theo ràng buộc từng nền tảng.
6. Tạo package bằng jpackage trên runner đúng OS.
7. Đọc metadata bên trong MSI, app bundle, DEB và RPM.
8. So sánh version package mới với bản đang phát hành.
9. Cài bản cũ rồi nâng cấp lên bản mới trên máy sạch.
10. Ký, xác minh và phát hành artifact đã qua kiểm thử.

Giữ cấu hình version và tên package trong pipeline dưới dạng biến được kiểm soát. Không tự ghép chuỗi version theo cách khác nhau trong từng job CI; hãy dùng một hàm ánh xạ có quy tắc rõ ràng và kiểm tra kết quả bằng package metadata.

## 22. Cách áp dụng trong quy trình Java hiện đại

- Dùng **--app-version** cho version ứng dụng và giữ revision package riêng.
- Giữ **--name** ổn định cho cùng một sản phẩm.
- Trên Windows, tuân thủ ProductVersion ba trường và giới hạn của MSI; giữ **--win-upgrade-uuid** ổn định.
- Trên macOS, giữ **--mac-package-identifier** ổn định; dùng version số hợp lệ cho Info.plist và kiểm tra cả CFBundleShortVersionString lẫn CFBundleVersion.
- Trên Linux, dùng **--linux-package-name** ổn định và **--linux-app-release** để quản lý revision DEB/RPM.
- Không dùng dấu gạch ngang trong RPM Version/Release; dùng quy tắc prerelease phù hợp với RPM.
- Với Debian, tuân thủ [epoch:]upstream_version[-debian_revision] và thuật toán so sánh của dpkg.
- Tách kênh beta khỏi stable nếu version constraint của Windows/macOS không thể biểu diễn hậu tố prerelease.
- Kiểm tra metadata package và thử nâng cấp thực tế trước khi phát hành.

Version và tên package quyết định cách hệ điều hành nhận diện, so sánh và nâng cấp ứng dụng. Dùng một nguồn version chuẩn, ánh xạ đúng giới hạn của từng định dạng installer và giữ ổn định package identity giúp bản phát hành Java có thể nâng cấp đáng tin cậy trên Windows, macOS và Linux.

## Tài liệu tham khảo

- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle JDK 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Microsoft Learn — ProductVersion property](https://learn.microsoft.com/en-us/windows/win32/msi/productversion)
- [Debian Policy — Control Files and Their Fields](https://www.debian.org/doc/debian-policy/ch-controlfields)
- [Debian Policy — Version field](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version)
- [RPM — Version System](https://rpm.org/docs/6.0.x/man/rpm-version.7)
- [RPM — Spec File Format](https://rpm.org/docs/latest/manual/spec.html)
- [Apple — CFBundleShortVersionString](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleshortversionstring)
- [Apple — CFBundleVersion](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleversion)
