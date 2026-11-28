# Chọn định dạng exe, msi, deb, rpm, dmg hoặc pkg theo nền tảng

Java 16 hoàn thiện công cụ `jpackage`, cho phép đóng gói ứng dụng Java thành bộ cài hoặc application image theo định dạng gốc của hệ điều hành. Thay vì yêu cầu người dùng tự tìm JAR, cài Java và chạy lệnh, bộ cài có thể tạo launcher, đưa ứng dụng vào vị trí cài đặt phù hợp và phân phối runtime Java đi kèm.

Các định dạng `exe`, `msi`, `deb`, `rpm`, `dmg` và `pkg` phục vụ những hệ điều hành và cách phân phối khác nhau. Không có một định dạng duy nhất phù hợp cho mọi nền tảng. Cần chọn theo hệ điều hành đích, thói quen cài đặt của người dùng, công cụ quản trị phần mềm của tổ chức, yêu cầu ký số và cách cập nhật ứng dụng.

Trong module Java 16, đóng gói JDK và ứng dụng là một phần quan trọng của quá trình đưa ứng dụng đến người dùng. Bài này tập trung vào các định dạng native installer vẫn được sử dụng hiện nay và cách chọn định dạng bằng `jpackage` đã ổn định từ Java 16. Các ví dụ không dựa vào cơ chế thử nghiệm hoặc quy trình phân phối đã lỗi thời.

## 1. Bản đồ định dạng theo hệ điều hành

| Hệ điều hành đích | Định dạng `jpackage` | Vai trò chính |
|---|---|---|
| Windows | `exe` | Trình cài đặt thực thi, thường phù hợp cho tải xuống và cài đặt trực tiếp. |
| Windows | `msi` | Gói Windows Installer, phù hợp với quy trình triển khai và quản trị phần mềm của tổ chức. |
| Linux dùng hệ Debian | `deb` | Gói cài đặt dành cho Debian, Ubuntu và các bản phân phối tương thích. |
| Linux dùng hệ RPM | `rpm` | Gói cài đặt dành cho Fedora, Red Hat Enterprise Linux, SUSE và các bản phân phối tương thích. |
| macOS | `dmg` | Disk image để phân phối ứng dụng, thường cho phép người dùng mở ảnh đĩa và kéo ứng dụng vào thư mục Applications. |
| macOS | `pkg` | Gói cài đặt của macOS Installer, phù hợp khi cần quy trình cài đặt có hướng dẫn và quản trị tập trung. |

`jpackage` còn có kiểu `app-image`. Đây là thư mục ứng dụng đã được đóng gói, không phải bộ cài native. Nó hữu ích để kiểm thử ứng dụng trước khi tạo installer hoặc để phân phối theo một quy trình nội bộ riêng.

## 2. Chọn giữa EXE và MSI trên Windows

### EXE: bộ cài thực thi cho người dùng cuối

Tệp `.exe` là chương trình cài đặt mà người dùng có thể chạy trực tiếp. Đây thường là lựa chọn thuận tiện khi phát hành ứng dụng trên trang tải xuống của sản phẩm hoặc cung cấp cho người dùng tự cài trên máy Windows.

Chọn EXE khi:

- Người dùng tải ứng dụng và tự chạy trình cài đặt.
- Muốn quy trình cài đặt có giao diện hướng dẫn quen thuộc.
- Kênh phân phối của tổ chức đã hỗ trợ triển khai installer dạng EXE và có hướng dẫn tham số cài đặt phù hợp.

EXE là định dạng thực thi. Chính sách kiểm soát ứng dụng của Windows hoặc phần mềm bảo mật của tổ chức có thể yêu cầu kiểm tra nhà phát hành và chữ ký số trước khi cho phép chạy.

### MSI: gói Windows Installer cho quản trị và triển khai

`.msi` là gói Windows Installer. Nó phù hợp với môi trường cần quản lý quá trình cài đặt, gỡ cài đặt và triển khai phần mềm bằng công cụ quản trị thiết bị hoặc hệ thống phân phối phần mềm của doanh nghiệp.

Chọn MSI khi:

- Bộ phận IT cần triển khai ứng dụng trên nhiều máy Windows.
- Quy trình quản trị yêu cầu gói Windows Installer.
- Cần tích hợp cài đặt và gỡ cài đặt với các công cụ quản lý phần mềm đang dùng.

MSI không tự động bảo đảm mọi chính sách nâng cấp hoặc cấu hình dữ liệu người dùng đều đúng. Cần kiểm tra cách phiên bản mới thay thế phiên bản cũ, cách xử lý shortcut, thư mục dữ liệu và quyền cài đặt trong môi trường thực tế.

### Ví dụ tạo EXE hoặc MSI

Hai lệnh sau dùng cùng đầu vào ứng dụng; chỉ khác định dạng đầu ra:

```bash
jpackage --type exe \
  --name InventoryApp \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
```

```bash
jpackage --type msi \
  --name InventoryApp \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
```

Trong ví dụ, `--input` chỉ thư mục chứa JAR và các file phụ thuộc cần đóng gói; `--main-jar` xác định JAR khởi chạy; `--main-class` chỉ lớp có phương thức `main`; `--dest` chỉ thư mục nhận bộ cài. Thay các giá trị minh họa bằng tên và đường dẫn của dự án.

## 3. Chọn giữa DEB và RPM trên Linux

Linux có nhiều bản phân phối và hệ thống quản lý gói. Chọn định dạng theo hệ package mà bản phân phối đích hỗ trợ.

### DEB: Debian, Ubuntu và các bản tương thích

`.deb` là định dạng gói của hệ Debian. Các công cụ như `apt` và `dpkg` sử dụng định dạng này để cài đặt, gỡ cài đặt và quản lý gói.

Chọn DEB khi ứng dụng hướng đến Debian, Ubuntu hoặc bản phân phối sử dụng hệ gói Debian. Khi phát hành, cần xác định rõ phiên bản hệ điều hành tối thiểu và các thư viện native mà ứng dụng cần.

Ví dụ:

```bash
jpackage --type deb \
  --name InventoryApp \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --linux-package-name inventory-app \
  --linux-deb-maintainer "Example Team <packages@example.com>" \
  --dest dist
```

`--linux-package-name` đặt tên gói trong hệ Linux; `--linux-deb-maintainer` khai báo thông tin đơn vị duy trì gói. Metadata cần phản ánh thông tin phát hành thực tế của ứng dụng.

### RPM: Fedora, RHEL và SUSE

`.rpm` là định dạng gói của hệ RPM. Các công cụ như `rpm`, `dnf` và `zypper` sử dụng định dạng này tùy bản phân phối.

Chọn RPM khi ứng dụng hướng đến Fedora, Red Hat Enterprise Linux, các bản tương thích RHEL hoặc SUSE. Cần kiểm tra phiên bản hệ điều hành, kiến trúc CPU, thư viện native và chính sách đóng gói của từng môi trường.

Ví dụ:

```bash
jpackage --type rpm \
  --name InventoryApp \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --linux-package-name inventory-app \
  --linux-rpm-license-type "Apache-2.0" \
  --dest dist
```

`--linux-rpm-license-type` khai báo loại giấy phép trong metadata của gói RPM. Hãy sử dụng giá trị phù hợp với giấy phép thực tế của ứng dụng và các thành phần được phân phối kèm.

### Không xem DEB và RPM là gói Linux dùng chung

Một file `.deb` không thay thế trực tiếp cho `.rpm`, và ngược lại. Cấu trúc metadata, dependency, script cài đặt và công cụ quản lý gói khác nhau. Nếu hỗ trợ cả hai hệ, hãy tạo và kiểm thử hai gói riêng.

Ngoài định dạng gói, cần kiểm tra thư viện hệ thống mà ứng dụng phụ thuộc. Một gói cài thành công trên một bản phân phối chưa chứng minh ứng dụng chạy được trên mọi bản phân phối Linux cùng định dạng.

## 4. Chọn giữa DMG và PKG trên macOS

### DMG: phân phối ứng dụng qua disk image

`.dmg` là ảnh đĩa của macOS. Người dùng mở file để xem nội dung, thường là ứng dụng có thể kéo vào thư mục Applications. Đây là cách phân phối quen thuộc cho ứng dụng desktop tải trực tiếp từ website.

Chọn DMG khi:

- Muốn cung cấp một file tải xuống để người dùng tự cài ứng dụng.
- Ứng dụng có cách cài đặt đơn giản, chủ yếu là đưa bundle ứng dụng vào Applications.
- Muốn kèm hướng dẫn ngắn hoặc nội dung giới thiệu trong cửa sổ disk image.

DMG là vật chứa phân phối, không phải cùng loại với package cài đặt của macOS Installer. Người dùng thường mở ảnh đĩa rồi thực hiện thao tác cài đặt theo hướng dẫn.

Ví dụ:

```bash
jpackage --type dmg \
  --name InventoryApp \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --mac-package-identifier com.example.inventory \
  --dest dist
```

### PKG: gói cài đặt của macOS Installer

`.pkg` là package mà macOS Installer có thể mở và thực hiện quy trình cài đặt. Định dạng này phù hợp khi cần trình cài đặt có hướng dẫn, vị trí cài đặt do package xác định hoặc triển khai qua hệ thống quản trị máy Mac.

Chọn PKG khi:

- Quy trình phát hành yêu cầu package cài đặt thay vì thao tác kéo ứng dụng từ disk image.
- Tổ chức cần triển khai ứng dụng theo quy trình cài đặt được quản lý.
- Cần thống nhất cách cài đặt với các package macOS khác đang được phân phối.

Ví dụ:

```bash
jpackage --type pkg \
  --name InventoryApp \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --mac-package-identifier com.example.inventory \
  --dest dist
```

`--mac-package-identifier` đặt định danh package theo dạng reverse-DNS. Hãy giữ định danh ổn định giữa các bản phát hành của cùng ứng dụng để hỗ trợ quản lý package và cập nhật.

## 5. Bảng so sánh nhanh

| Định dạng | Nền tảng | Trải nghiệm chính | Phù hợp khi |
|---|---|---|---|
| EXE | Windows | Chạy trình cài đặt thực thi | Phân phối trực tiếp cho người dùng hoặc kênh đã hỗ trợ EXE. |
| MSI | Windows | Windows Installer quản lý package | Triển khai tập trung và quản trị thiết bị. |
| DEB | Debian/Ubuntu và tương thích | Cài qua hệ package Debian | Phát hành cho môi trường dùng `apt`/`dpkg`. |
| RPM | Fedora/RHEL/SUSE và tương thích | Cài qua hệ package RPM | Phát hành cho môi trường dùng `dnf`/`rpm`/`zypper`. |
| DMG | macOS | Mở disk image rồi cài ứng dụng | Tải trực tiếp và cài thủ công trên máy Mac. |
| PKG | macOS | macOS Installer thực hiện cài đặt | Cài đặt có hướng dẫn hoặc triển khai được quản lý. |

## 6. Cách chọn theo kênh phân phối

Hãy bắt đầu từ môi trường người dùng sẽ cài ứng dụng:

1. **Máy Windows cá nhân:** chọn EXE nếu người dùng tải và chạy installer trực tiếp; chọn MSI nếu kênh phân phối hoặc chính sách IT yêu cầu Windows Installer.
2. **Máy Windows trong doanh nghiệp:** kiểm tra công cụ quản trị phần mềm của tổ chức. Nếu quy trình tiêu chuẩn nhận MSI, phát hành MSI và kiểm thử cài đặt/gỡ cài đặt theo chính sách đó.
3. **Máy Linux Debian/Ubuntu:** tạo DEB và xác định các phiên bản bản phân phối được hỗ trợ.
4. **Máy Linux Fedora/RHEL/SUSE:** tạo RPM và kiểm tra dependency trên từng họ bản phân phối đích.
5. **Máy Mac của người dùng cuối:** chọn DMG nếu muốn trải nghiệm tải về và kéo ứng dụng vào Applications.
6. **Máy Mac do tổ chức quản lý:** cân nhắc PKG nếu quy trình triển khai yêu cầu package Installer.

Nếu cần hỗ trợ nhiều nền tảng, phát hành nhiều artifact riêng. Ví dụ, một sản phẩm desktop có thể cung cấp EXE và MSI cho Windows, DEB và RPM cho Linux, DMG và PKG cho macOS. Không yêu cầu người dùng đổi định dạng để dùng chung một file trên các hệ điều hành khác nhau.

## 7. Đóng gói runtime Java cùng ứng dụng

Native installer có thể phân phối ứng dụng cùng runtime Java để người dùng không phải tự cài một JDK riêng. Điều này giúp kiểm soát phiên bản runtime mà ứng dụng sử dụng và giảm khác biệt giữa các máy.

Có thể tạo runtime tùy chỉnh bằng `jlink`, sau đó truyền vào `jpackage` qua `--runtime-image`:

```bash
jlink \
  --add-modules java.base,java.desktop,java.logging \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
```

Danh sách module trong ví dụ chỉ mang tính minh họa. Hãy xác định đầy đủ module mà ứng dụng và thư viện phụ thuộc cần dùng; ứng dụng thực tế có thể cần thêm module như `java.sql`, `java.net.http`, `jdk.crypto.ec` hoặc các module khác.

Sau đó tạo bộ cài và đính kèm runtime:

```bash
jpackage --type msi \
  --name InventoryApp \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --runtime-image build/runtime \
  --dest dist
```

Nếu không tự cung cấp runtime image, `jpackage` có thể tạo runtime image trong quá trình đóng gói bằng công cụ `jlink` đi kèm JDK. Với ứng dụng cần kiểm soát chính xác tập module, kích thước và cấu hình runtime, nên tạo và kiểm thử runtime image riêng trước khi đóng gói.

Đóng gói runtime làm tăng dung lượng bộ cài nhưng giúp ứng dụng dùng đúng runtime đã kiểm thử. Nếu không đóng gói runtime, tài liệu cài đặt phải nêu rõ phiên bản Java tương thích mà người dùng cần chuẩn bị. Dù chọn cách nào, cần cập nhật runtime theo các bản vá bảo mật và phát hành lại ứng dụng khi cần.

## 8. Xây dựng trên đúng nền tảng đích

`jpackage` tạo định dạng native dựa trên nền tảng đang chạy. Quy trình phát hành cần có môi trường build tương ứng:

- Tạo EXE hoặc MSI trên Windows.
- Tạo DEB hoặc RPM trên Linux có công cụ đóng gói tương ứng.
- Tạo DMG hoặc PKG trên macOS.

Không nên giả định có thể chạy một lệnh trên Windows rồi tạo ra bộ cài macOS hoặc Linux hoàn chỉnh. Hãy dùng máy build hoặc runner CI phù hợp với hệ điều hành đích. Nếu ứng dụng hỗ trợ nhiều kiến trúc CPU, tạo và kiểm thử artifact tương ứng với từng kiến trúc được công bố.

Ngoài hệ điều hành, cần thống nhất phiên bản JDK dùng để build, kiến trúc của JDK và runtime image, kiến trúc máy đích, cùng các thư viện native đi kèm. Runtime image dành cho một hệ điều hành hoặc kiến trúc không thể tùy tiện dùng cho hệ khác.

## 9. Ký số và niềm tin của hệ điều hành

Installer được tạo ra chưa có nghĩa là đã sẵn sàng phát hành công khai. Các hệ điều hành có cơ chế xác minh nhà phát hành và nguồn gốc phần mềm:

- **Windows:** ký số EXE và MSI bằng chứng thư phù hợp để người dùng và công cụ quản trị có thể xác minh nhà phát hành, đồng thời giảm cảnh báo không rõ nguồn gốc. Kiểm tra chữ ký sau khi đóng gói và trước khi phát hành.
- **macOS:** ứng dụng phân phối bên ngoài Mac App Store thường cần quy trình code signing bằng Developer ID và notarization để đáp ứng Gatekeeper. Kiểm tra cả ứng dụng bên trong bundle và artifact phân phối theo yêu cầu của kênh phát hành.
- **Linux:** dùng cơ chế xác thực của kênh phân phối. Khi phát hành qua repository, bảo vệ metadata repository bằng chữ ký và cung cấp package từ nguồn tin cậy; với RPM, có thể áp dụng chữ ký package theo chính sách của hệ thống.

Quy trình ký số cần được thực hiện bằng chứng thư và khóa do tổ chức quản lý. Không đưa private key vào source code, file cấu hình công khai hoặc artifact phát hành.

## 10. Phiên bản, nâng cấp và gỡ cài đặt

Chọn đúng định dạng chỉ là bước đầu. Người dùng còn cần nâng cấp và gỡ ứng dụng mà không mất dữ liệu ngoài dự kiến.

Trước khi phát hành, xác định:

- Tên ứng dụng, phiên bản và định danh package có ổn định giữa các bản phát hành hay không.
- Bản mới sẽ nâng cấp bản cũ, cài song song hay yêu cầu gỡ bản cũ trước.
- Shortcut, launcher, file liên kết và thư mục cài đặt được tạo hoặc cập nhật thế nào.
- Dữ liệu người dùng và cấu hình lưu ở đâu, có được giữ lại khi gỡ cài đặt không.
- Runtime Java được cập nhật cùng ứng dụng hay theo một quy trình riêng.
- Cách xử lý khi cài đặt thất bại hoặc cần quay lại phiên bản trước.

Không lưu dữ liệu người dùng duy nhất bên trong thư mục cài đặt nếu quá trình nâng cấp hoặc gỡ cài đặt có thể thay thế hay xóa thư mục đó. Hãy tách dữ liệu cần giữ lâu dài khỏi file chương trình và kiểm thử chính sách uninstall trên máy sạch.

## 11. Kiểm thử artifact trước khi phát hành

Với mỗi định dạng, kiểm tra trên hệ điều hành và phiên bản được hỗ trợ:

1. Cài mới trên máy sạch hoặc máy ảo tương đương môi trường người dùng.
2. Khởi chạy launcher, xác nhận ứng dụng tìm thấy runtime và tài nguyên cần thiết.
3. Kiểm tra shortcut, menu ứng dụng, icon và vị trí cài đặt nếu sản phẩm cung cấp các thành phần đó.
4. Kiểm tra quyền người dùng thường và quyền quản trị theo kiểu cài đặt dự kiến.
5. Nâng cấp từ phiên bản trước và xác minh dữ liệu, cấu hình được xử lý đúng.
6. Gỡ cài đặt, xác minh file chương trình được dọn đúng và dữ liệu người dùng được giữ hoặc xóa theo chính sách đã công bố.
7. Kiểm tra chữ ký số, cảnh báo bảo mật và log của hệ điều hành.
8. Kiểm tra trên các kiến trúc CPU và bản phân phối cụ thể mà sản phẩm cam kết hỗ trợ.

`jpackage --type app-image` có thể tạo application image để kiểm tra launcher và runtime trước khi tạo installer. Tuy nhiên, kiểm thử app-image không thay thế kiểm thử cài đặt, nâng cấp và gỡ cài đặt của EXE, MSI, DEB, RPM, DMG hoặc PKG.

## 12. Bảng quyết định nhanh

| Câu hỏi | Lựa chọn nên cân nhắc |
|---|---|
| Người dùng Windows tải và tự cài? | EXE |
| Công cụ triển khai Windows của tổ chức yêu cầu Windows Installer? | MSI |
| Máy Linux đích dùng hệ Debian? | DEB |
| Máy Linux đích dùng hệ RPM? | RPM |
| Người dùng Mac tải về và kéo ứng dụng vào Applications? | DMG |
| Quy trình Mac yêu cầu package cài đặt của Installer? | PKG |
| Cần kiểm tra bundle trước khi tạo installer? | `app-image` |
| Cần ứng dụng dùng runtime Java đã kiểm thử? | Đóng gói runtime image cùng ứng dụng |

## 13. Cách áp dụng trong quy trình phát hành Java hiện đại

- Xác định hệ điều hành, kiến trúc CPU và các phiên bản nền tảng được hỗ trợ trước khi chọn định dạng.
- Chọn EXE/MSI, DEB/RPM hoặc DMG/PKG theo cách người dùng và bộ phận IT triển khai phần mềm.
- Dùng `jpackage` của JDK 16 trở lên; đây là công cụ đã được hoàn thiện trong Java 16, không cần bật preview.
- Dùng `jlink` khi cần tạo runtime image tùy chỉnh và chuyển image vào `jpackage` bằng `--runtime-image`.
- Build artifact trên nền tảng đích và kiểm thử trên hệ điều hành thực tế.
- Giữ ổn định tên, phiên bản và định danh package; kiểm thử nâng cấp và gỡ cài đặt.
- Ký số artifact theo yêu cầu của Windows, macOS hoặc repository Linux trước khi phân phối.
- Phát hành riêng từng định dạng và ghi rõ nền tảng, kiến trúc, phiên bản hệ điều hành được hỗ trợ.

Chọn định dạng native installer theo nền tảng giúp người dùng cài ứng dụng bằng công cụ quen thuộc của hệ điều hành. `jpackage` cung cấp quy trình đóng gói nhất quán cho ứng dụng Java, còn việc chọn EXE, MSI, DEB, RPM, DMG hay PKG phụ thuộc vào kênh phân phối, quản trị thiết bị và yêu cầu vận hành thực tế. Kết hợp runtime được kiểm thử, ký số và kiểm tra nâng cấp/gỡ cài đặt sẽ tạo ra bộ cài phù hợp để phát hành lâu dài.
