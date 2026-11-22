# Tên ứng dụng trong jpackage

**jpackage** là công cụ của JDK dùng để đóng gói ứng dụng Java thành application image hoặc bộ cài native theo hệ điều hành. Tùy chọn **--name** (viết tắt **-n**) đặt tên ứng dụng và/hoặc package. Tên này được dùng làm cơ sở cho nhiều thành phần do jpackage tạo ra, chẳng hạn tên launcher chính, thư mục ứng dụng và tên package. Tên package cuối cùng thường kết hợp tên ứng dụng với phiên bản.

Ví dụ:

~~~bash
jpackage --type app-image --name AcmeDesk --app-version 2.4.0 --input input --main-jar acme-desk.jar --main-class com.acme.Main --dest dist
~~~

Ở đây, **AcmeDesk** là tên ứng dụng được đóng gói; **2.4.0** là phiên bản; **dist** là nơi đặt output. Tên ứng dụng không xác định class main được chạy. Điểm vào chương trình vẫn do **--main-jar**, **--main-class** hoặc **--module** quyết định.

## 1. --name dùng để làm gì?

Cú pháp:

~~~bash
jpackage --name application-name
~~~

Hoặc dùng dạng ngắn:

~~~bash
jpackage -n application-name
~~~

Theo tài liệu jpackage, --name là tên của application và/hoặc package. Đây là tên nhận diện sản phẩm trong quá trình đóng gói. Tùy nền tảng và loại output, tên này có thể ảnh hưởng đến:

- Tên application image hoặc thư mục ứng dụng được tạo.
- Tên launcher chính mà người dùng chạy.
- Tên file bộ cài khi kết hợp với app version và phần mở rộng của package.
- Tên thư mục cài đặt mặc định.
- Tên Linux package nếu không đặt tùy chọn riêng.
- Tên ứng dụng hiển thị ở một số thành phần giao diện nền tảng.
- Tên file resource override được jpackage tìm theo launcher/application name.

Vì vậy, hãy chọn một tên ngắn gọn, ổn định và dễ nhận biết. Với sản phẩm phát hành lâu dài, nên dùng cùng một tên sản phẩm giữa các phiên bản; quản lý số phiên bản bằng --app-version.

Tên có thể chứa khoảng trắng nếu được shell truyền như một đối số duy nhất. Ví dụ:

~~~bash
jpackage --name "Acme Desk" --type app-image ...
~~~

Trong script build, hãy đặt dấu nháy quanh giá trị có khoảng trắng hoặc ký tự đặc biệt để shell không tách thành nhiều đối số.

## 2. Nếu không chỉ định --name

Nếu bỏ qua --name, jpackage lấy tên mặc định từ đầu vào chính, thường là tên main JAR hoặc module. Phiên bản ứng dụng mặc định là **1.0**. Tên package được tạo từ tên ứng dụng và phiên bản, sau đó có phần mở rộng phụ thuộc loại package.

Ví dụ với ứng dụng không modular có main JAR là HelloWorld.jar trên Windows:

~~~bash
jpackage --input app --main-jar HelloWorld.jar
~~~

Tài liệu Oracle minh họa package mặc định có tên:

~~~text
HelloWorld-1.0.exe
~~~

Nếu tên JAR hoặc module mang tính kỹ thuật, tên mặc định có thể không phù hợp với tên sản phẩm muốn đưa cho người dùng. Khi phát hành, nên truyền --name tường minh để tránh phụ thuộc tên file build hoặc tên module.

Có thể dùng --help để xem tùy chọn mà bản jpackage hiện tại hỗ trợ:

~~~bash
jpackage --help
jpackage --version
~~~

## 3. Phân biệt tên ứng dụng với các tên khác

Trong jpackage, nhiều tùy chọn có chứa từ name hoặc identifier nhưng chúng giải quyết các mục đích khác nhau.

| Tùy chọn | Ý nghĩa | Ví dụ |
|---|---|---|
| --name | Tên application/package chính | AcmeDesk |
| --app-version | Phiên bản sản phẩm/package | 2.4.0 |
| --dest | Thư mục đặt output do jpackage tạo | dist |
| --install-dir | Thư mục cài ứng dụng trên máy người dùng | Acme |
| --main-jar | JAR chứa main class | acme-desk.jar |
| --main-class | Tên đầy đủ của main class | com.acme.Main |
| --module | Module chính và có thể kèm main class | com.acme.app/com.acme.Main |
| --linux-package-name | Tên package riêng trên Linux | acme-desk |
| --mac-package-identifier | Định danh duy nhất của app trên macOS | com.acme.desk |
| --mac-package-name | Tên ứng dụng xuất hiện trên menu bar macOS | Acme Desk |

Các điểm cần nhớ:

- --name đặt tên sản phẩm được đóng gói.
- --main-class hoặc --module xác định điểm vào của chương trình.
- --app-version quản lý phiên bản.
- --dest chỉ đổi nơi lưu output.
- --install-dir đổi vị trí cài đặt mặc định.
- Các tùy chọn nền tảng có thể đặt tên package hoặc identifier riêng.

Không dùng tên class main làm tên sản phẩm chỉ vì cả hai cùng xuất hiện trong lệnh đóng gói. Một ứng dụng có thể có class main là com.acme.bootstrap.Launcher nhưng tên người dùng nhìn thấy là AcmeDesk.

## 4. Tên ứng dụng, phiên bản và tên file package

Tùy chọn --app-version đặt phiên bản ứng dụng và/hoặc package. Nếu không chỉ định, phiên bản mặc định là 1.0.

Ví dụ trên Windows:

~~~bash
jpackage --type exe --name AcmeDesk --app-version 2.4.0 --input input --main-jar acme-desk.jar --dest dist
~~~

Tên package được tạo từ tên và phiên bản, ví dụ:

~~~text
AcmeDesk-2.4.0.exe
~~~

Nếu phát hành bản tiếp theo, giữ tên sản phẩm và thay phiên bản:

~~~bash
jpackage --type exe --name AcmeDesk --app-version 2.5.0 --input input --main-jar acme-desk.jar --dest dist
~~~

Package mới có thể có tên:

~~~text
AcmeDesk-2.5.0.exe
~~~

Việc tách tên và version giúp:

- Tên sản phẩm nhất quán qua các lần phát hành.
- Dễ phân biệt artifact giữa các phiên bản.
- Tránh đổi launcher hoặc thư mục ứng dụng chỉ vì version thay đổi.
- Dễ viết script CI/CD và lưu trữ artifact theo version.

Tên file package chính xác còn phụ thuộc hệ điều hành và package type. Hãy kiểm tra file được tạo trong --dest thay vì giả định mọi nền tảng có cùng quy tắc đặt tên.

## 5. Tên ứng dụng ảnh hưởng đến launcher

Theo mặc định, tên launcher chính lấy từ tên ứng dụng. Ví dụ, nếu dùng:

~~~bash
jpackage --type app-image --name AcmeDesk --input input --main-jar acme-desk.jar --dest dist
~~~

Application image sẽ có launcher mang tên AcmeDesk theo quy tắc của hệ điều hành. Các ví dụ cấu trúc phổ biến:

~~~text
Windows:
AcmeDesk/
  AcmeDesk.exe
  app/
  runtime/

Linux:
AcmeDesk/
  bin/
    AcmeDesk
  lib/
  runtime/

macOS:
AcmeDesk.app/
  Contents/
    MacOS/
      AcmeDesk
    Resources/
    app/
    runtime/
~~~

Tên và cấu trúc file chi tiết có thể thay đổi theo nền tảng và phiên bản jpackage. Các file nội bộ trong application image là implementation detail; không nên viết script phụ thuộc vào cấu trúc nội bộ chưa được tài liệu hóa.

### Tạo nhiều launcher

Một ứng dụng có thể cung cấp nhiều launcher cho các tác vụ khác nhau. Dùng **--add-launcher** với cú pháp:

~~~bash
jpackage --add-launcher launcher-name=properties-file
~~~

Tên đứng trước dấu bằng là tên launcher bổ sung. File properties chứa cấu hình riêng như module, main-jar, main-class, description, arguments, java-options hoặc icon.

Ví dụ file **diagnostics.properties**:

~~~properties
main-jar=acme-desk.jar
main-class=com.acme.tools.Diagnostics
description=Acme Desk Diagnostics
arguments=--support-mode
~~~

Tạo application image với launcher chính và launcher phụ:

~~~bash
jpackage --type app-image --name AcmeDesk --input input --main-jar acme-desk.jar --add-launcher Diagnostics=diagnostics.properties --dest dist
~~~

Trong image, launcher chính dùng tên AcmeDesk; launcher bổ sung có tên Diagnostics theo nền tảng. --add-launcher không đổi tên sản phẩm chính. Nếu cần thay tên launcher chính, đặt --name.

Có thể dùng --add-launcher nhiều lần để tạo nhiều launcher phụ. Hãy chọn tên ngắn, rõ chức năng và tránh tên trùng nhau.

## 6. Tên thư mục output và thư mục cài đặt

Hai tùy chọn thường bị nhầm:

- **--dest**: nơi jpackage ghi application image hoặc file package trên máy build.
- **--install-dir**: thư mục ứng dụng được cài trên máy người dùng đối với các package type hỗ trợ.

Ví dụ:

~~~bash
jpackage --type app-image --name AcmeDesk --input input --main-jar acme-desk.jar --dest build-output
~~~

Lệnh đặt output trong build-output. Nó không chỉ định thư mục cài đặt sau khi người dùng chạy installer.

Ví dụ package installer:

~~~bash
jpackage --type exe --name AcmeDesk --install-dir "Acme Tools/AcmeDesk" --input input --main-jar acme-desk.jar --dest packages
~~~

--install-dir điều khiển vị trí cài đặt theo quy tắc của hệ điều hành. Trên Windows, giá trị thường là một đường dẫn con bên dưới installation root; trên Linux hoặc macOS, có thể chỉ định đường dẫn cài đặt phù hợp. Hãy xem trợ giúp của đúng nền tảng vì ý nghĩa đường dẫn và quyền cài đặt khác nhau.

Theo hướng dẫn packaging của Oracle, thư mục cài đặt mặc định thường dựa trên tên ứng dụng:

| Nền tảng | Vị trí mặc định minh họa |
|---|---|
| Linux | /opt/application-name |
| macOS | /Applications/application-name |
| Windows | C:\\Program Files\\application-name |
| Windows cài theo user | AppData\\Local\\application-name trong profile người dùng |

Nếu muốn thư mục cài đặt khác tên sản phẩm, dùng --install-dir. Thay đổi --dest không thay đổi nơi ứng dụng được cài trên máy đích.

## 7. Tên package riêng trên Linux

Trên Linux, **--linux-package-name** cho phép đặt tên package khác với tên application:

~~~bash
jpackage --type deb --name "Acme Desk" --linux-package-name acme-desk --input input --main-jar acme-desk.jar --dest packages
~~~

Trong ví dụ:

- Tên application là Acme Desk.
- Tên package của hệ thống là acme-desk.
- Output là gói DEB trong thư mục packages.

Nếu không chỉ định --linux-package-name, tên package mặc định là tên application.

Tên hiển thị cho người dùng và tên package manager có mục đích khác nhau. Tên application có thể thân thiện, có chữ hoa hoặc khoảng trắng; tên package nên tuân theo quy tắc đặt tên của định dạng DEB/RPM và chính sách phân phối của tổ chức. Kiểm tra metadata package sau khi tạo để xác nhận tên chính xác.

Linux hỗ trợ các package type như DEB và RPM. Tên package có thể ảnh hưởng đến tên file, metadata và thao tác quản lý package trên máy người dùng. Nếu cần giữ định danh package ổn định qua các lần nâng cấp, hãy duy trì cùng tên package và quản lý version/release riêng.

## 8. Tên và identifier riêng trên macOS

macOS có một số khái niệm tên khác nhau:

- **--name**: tên application chính.
- **--mac-package-identifier**: định danh duy nhất của ứng dụng trong hệ sinh thái macOS.
- **--mac-package-name**: tên ứng dụng hiển thị trên menu bar và cửa sổ Info.

Ví dụ:

~~~bash
jpackage --type dmg --name AcmeDesk --mac-package-identifier com.acme.desk --mac-package-name "Acme Desk" --input input --main-jar acme-desk.jar --dest packages
~~~

### mac-package-identifier

Identifier mặc định lấy từ main class name. Có thể đặt tường minh bằng --mac-package-identifier.

Tài liệu jpackage quy định identifier chỉ dùng các ký tự chữ và số ASCII, dấu gạch nối và dấu chấm. Ví dụ dạng reverse-DNS:

~~~text
com.acme.desk
~~~

Identifier dùng để nhận diện ứng dụng trên macOS. Nên giữ ổn định giữa các bản phát hành của cùng sản phẩm, đặc biệt khi có code signing, notarization hoặc cơ chế quản lý cập nhật.

Identifier không phải tên hiển thị trong Finder hoặc tên launcher. Đổi identifier có thể ảnh hưởng cách hệ điều hành nhận diện bundle và quy trình ký/cập nhật.

### mac-package-name

Tùy chọn --mac-package-name đặt tên xuất hiện trên menu bar và cửa sổ Info. Tên này có thể khác application name và phải ngắn hơn 16 ký tự.

Ví dụ:

~~~bash
jpackage --name AcmeDesk --mac-package-name "Acme Desk" ...
~~~

Tên menu bar cần ngắn gọn để hiển thị phù hợp. Theo tài liệu lệnh JDK 26, giá trị mặc định của mac-package-name là application name.

## 9. Tên ứng dụng trên Windows

Trên Windows, tên ứng dụng thường được dùng làm cơ sở cho:

- Tên thư mục application image.
- Tên launcher executable.
- Tên package/installer khi kết hợp version.
- Thư mục cài đặt mặc định.
- Tên một số shortcut hoặc mục menu nếu các tùy chọn tương ứng được bật.

Ví dụ tạo installer EXE:

~~~powershell
jpackage --type exe --name AcmeDesk --app-version 2.4.0 --input input --main-jar acme-desk.jar --win-menu --win-shortcut --dest packages
~~~

Tùy chọn --win-menu yêu cầu tạo mục Start Menu; --win-shortcut yêu cầu tạo desktop shortcut. Tên launcher mặc định dựa trên tên application.

Nếu cần thay đổi vị trí cài đặt hoặc cho người dùng chọn thư mục, xem --install-dir và --win-dir-chooser. Nếu cần installer cài theo user hiện tại, xem --win-per-user-install.

### Win upgrade UUID

--win-upgrade-uuid là UUID liên quan đến việc nâng cấp package trên Windows. Nó là một định danh kỹ thuật của installer, khác tên application. Với cùng một sản phẩm và cùng upgrade family, hãy quản lý UUID nhất quán theo chính sách phát hành; không dùng UUID này thay cho --name.

Ví dụ:

~~~powershell
jpackage --type msi --name AcmeDesk --app-version 2.4.0 --win-upgrade-uuid 12345678-1234-1234-1234-1234567890ab --input input --main-jar acme-desk.jar --dest packages
~~~

UUID trong ví dụ chỉ là giá trị minh họa; dự án thực tế phải tạo và quản lý UUID của sản phẩm theo quy trình release.

## 10. Tên ứng dụng trong resource directory

Tùy chọn **--resource-dir** cho phép cung cấp resource tùy chỉnh cho jpackage, chẳng hạn icon hoặc template của installer.

~~~bash
jpackage --name AcmeDesk --resource-dir packaging-resources ...
~~~

Một số resource được tìm theo tên launcher hoặc application:

| Nền tảng / mục đích | Tên file được jpackage tìm |
|---|---|
| Linux launcher icon | launcher-name.png |
| Linux desktop file | launcher-name.desktop |
| Windows launcher icon | launcher-name.ico |
| Windows launcher properties | launcher-name.properties |
| macOS launcher icon | launcher-name.icns |
| macOS entitlements | application-name.entitlements |

Ví dụ, nếu tên launcher chính là AcmeDesk, resource icon có thể đặt tên:

~~~text
packaging-resources/
  AcmeDesk.ico
~~~

Với launcher bổ sung Diagnostics, resource riêng có thể mang tên Diagnostics.ico trên Windows, Diagnostics.png trên Linux hoặc Diagnostics.icns trên macOS.

Tên file resource cần khớp với tên launcher/application mà jpackage đang dùng. Khi đổi --name hoặc --add-launcher, hãy rà soát resource directory để icon và template vẫn được tìm thấy.

Resource directory cũng có các file template dành riêng cho từng loại installer. Không phải mọi file trong resource directory đều được dùng trên mọi hệ điều hành.

## 11. Tên ứng dụng và loại package

Nếu không chỉ định --type, jpackage chọn loại package mặc định theo nền tảng. Các loại phổ biến:

| Nền tảng | Package type thường dùng |
|---|---|
| Windows | exe, msi |
| Linux | deb, rpm |
| macOS | dmg, pkg |
| Mọi nền tảng hỗ trợ | app-image |

Tên package được tạo từ application name và version theo quy tắc của package type. Ví dụ một Windows EXE có thể mang dạng AcmeDesk-2.4.0.exe; gói Linux có phần mở rộng .deb hoặc .rpm; macOS có thể tạo .dmg hoặc .pkg.

Để kiểm tra ứng dụng trước khi tạo installer, nên tạo app image:

~~~bash
jpackage --type app-image --name AcmeDesk --app-version 2.4.0 --input input --main-jar acme-desk.jar --dest image-output
~~~

Sau khi thử launcher và resource, tạo package native trên nền tảng đích:

~~~bash
jpackage --type deb --name AcmeDesk --app-version 2.4.0 --input input --main-jar acme-desk.jar --dest packages
~~~

jpackage không hỗ trợ cross-platform packaging. Muốn tạo installer Windows, Linux và macOS, hãy chạy jpackage trên từng hệ điều hành đích với cấu hình tên/version nhất quán.

## 12. Ví dụ hoàn chỉnh cho ứng dụng không modular

Giả sử có cấu trúc:

~~~text
project/
  input/
    acme-desk.jar
    config/
      app.properties
  packages/
~~~

JAR có main class trong manifest hoặc biết rõ class com.acme.Main. Tạo application image:

~~~bash
jpackage --type app-image --name AcmeDesk --app-version 2.4.0 --vendor "Acme Software" --description "Acme desktop application" --input input --main-jar acme-desk.jar --main-class com.acme.Main --dest packages
~~~

Giải thích:

- --name AcmeDesk đặt tên sản phẩm.
- --app-version 2.4.0 đặt version.
- --vendor và --description thêm metadata.
- --input chỉ định thư mục chứa JAR và resource.
- --main-jar chỉ định JAR chính tương đối với input directory.
- --main-class chỉ định main class nếu không được xác định trong manifest.
- --dest đặt nơi lưu application image.

Nếu main class đã được khai báo trong manifest, có thể bỏ --main-class.

Kiểm tra application image bằng launcher được tạo trong output. Nếu ứng dụng đọc resource theo đường dẫn tương đối, hãy kiểm tra working directory và cách truy cập resource trong môi trường đóng gói.

## 13. Ví dụ hoàn chỉnh cho ứng dụng modular

Với ứng dụng modular, chỉ định module path và main module:

~~~bash
jpackage --type app-image --name AcmeDesk --app-version 2.4.0 --module-path mods --module com.acme.app/com.acme.app.Main --dest packages
~~~

Trong ví dụ:

- --name đặt tên sản phẩm.
- --module-path chỉ nơi tìm các module.
- --module chỉ định module chính và main class.
- --dest đặt nơi lưu application image.

Không dùng đồng thời --module và --main-jar trong cùng cấu hình. Chọn một mô hình đóng gói phù hợp với ứng dụng: modular hoặc non-modular.

Nếu muốn thêm module vào runtime image do jpackage tạo, xem --add-modules và --jlink-options. Nếu đã có runtime image tự tạo bằng jlink, có thể truyền --runtime-image để jpackage sử dụng image đó.

## 14. Quy trình chọn tên ứng dụng cho dự án

1. Chọn tên sản phẩm ngắn, dễ đọc và ổn định, ví dụ AcmeDesk.
2. Dùng --name tường minh trong build script thay vì phụ thuộc tên JAR/module.
3. Đặt version bằng --app-version và thay đổi nó ở mỗi lần phát hành.
4. Xác định launcher chính có cần trùng tên sản phẩm hay không; nếu có nhiều launcher, đặt tên phụ bằng --add-launcher.
5. Xác định tên package Linux riêng nếu cần --linux-package-name.
6. Chọn macOS bundle identifier ổn định bằng --mac-package-identifier và tên menu bar ngắn bằng --mac-package-name.
7. Dùng --install-dir khi thư mục cài đặt cần khác tên application.
8. Đặt icon và template trong --resource-dir theo đúng tên application/launcher.
9. Tạo --type app-image trước để thử launcher, resource và runtime.
10. Tạo installer trên từng nền tảng đích và kiểm tra metadata sau khi đóng gói.

Một quy ước hữu ích là giữ tên sản phẩm và identifier ổn định trong suốt vòng đời sản phẩm, còn version, package release và vị trí output được quản lý riêng. Điều này giúp cập nhật ứng dụng dễ dự đoán hơn.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Package mang tên JAR/module thay vì tên sản phẩm | Không chỉ định --name | Đặt --name tường minh |
| Tên package có version không đúng | Thiếu hoặc sai --app-version | Kiểm tra app version và output filename |
| Launcher không mang tên mong muốn | Tên application hoặc cấu hình launcher phụ khác dự kiến | Kiểm tra --name và --add-launcher |
| Icon không được thay thế | Tên file icon không khớp launcher name hoặc sai resource directory | Kiểm tra tên file theo nền tảng |
| Linux package có tên không phù hợp | Tên package mặc định lấy từ application name | Đặt --linux-package-name phù hợp |
| macOS bundle identifier sai | Nhầm --name với --mac-package-identifier | Đặt identifier riêng, ổn định |
| Tên menu bar quá dài | --mac-package-name dài từ 16 ký tự trở lên | Chọn tên ngắn hơn 16 ký tự |
| Installer được lưu sai nơi | Nhầm --dest với --install-dir | Dùng --dest cho máy build, --install-dir cho máy cài |
| Đổi tên ứng dụng làm script resource hỏng | File override vẫn dùng tên launcher cũ | Cập nhật resource directory theo tên mới |
| Không thể tạo package cho hệ điều hành khác | jpackage build theo nền tảng hiện tại | Chạy build trên từng hệ điều hành đích |

## 16. Checklist trước khi phát hành

- [ ] --name được đặt tường minh và thống nhất trong build pipeline.
- [ ] --app-version đúng với version release.
- [ ] Main JAR/class hoặc module được chỉ định chính xác.
- [ ] Tên launcher chính và launcher phụ được kiểm tra trên application image.
- [ ] --dest và --install-dir được cấu hình đúng mục đích.
- [ ] Linux package name được đặt riêng nếu cần.
- [ ] macOS package identifier ổn định và menu name dưới 16 ký tự.
- [ ] Resource icon/template có tên khớp application hoặc launcher.
- [ ] Package type phù hợp nền tảng và installer được build trên hệ điều hành đích.
- [ ] Installer được cài thử trên môi trường sạch và xác nhận shortcut, launcher, version metadata.
- [ ] Các bản cập nhật giữ định danh sản phẩm phù hợp với chính sách upgrade của từng nền tảng.

## 17. Ghi nhớ

- **--name** hoặc **-n** đặt tên application và/hoặc package trong jpackage.
- Nếu bỏ --name, tên mặc định được suy ra từ main JAR hoặc module; version mặc định là 1.0.
- Tên package thường kết hợp application name và app version.
- Tên launcher chính và thư mục cài đặt mặc định thường dựa trên application name.
- **--dest** đặt thư mục output trên máy build; **--install-dir** điều khiển thư mục cài trên máy đích.
- **--main-jar**, **--main-class** và **--module** xác định điểm vào ứng dụng, không phải tên sản phẩm.
- Linux có **--linux-package-name**; macOS có **--mac-package-identifier** và **--mac-package-name**.
- **--add-launcher** đặt tên cho launcher bổ sung.
- Tên application/launcher có thể ảnh hưởng tên file icon và resource override.
- Hãy kiểm tra application image trước khi tạo installer native và build trên đúng nền tảng đích.

## Tài liệu tham khảo chính thức

- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Basic Packaging — JDK 25](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html)
- [Packaging Tool User's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/index.html)