# Metadata, shortcut và dependency hệ điều hành cho gói Linux

Khi đóng gói ứng dụng Java thành DEB hoặc RPM bằng **jpackage**, cần khai báo metadata của package, cách ứng dụng xuất hiện trong menu desktop và các thư viện hệ thống mà ứng dụng yêu cầu. Những thông tin này giúp package manager nhận diện gói, hiển thị thông tin phát hành, kiểm tra dependency và hỗ trợ người dùng tìm launcher sau khi cài đặt.

Các tùy chọn Linux quan trọng gồm **--linux-package-name**, **--linux-deb-maintainer**, **--linux-menu-group**, **--linux-package-deps**, **--linux-rpm-license-type**, **--linux-app-release**, **--linux-app-category** và **--linux-shortcut**. Một số tùy chọn chỉ có ý nghĩa với DEB hoặc RPM; không nên áp dụng máy móc cùng một giá trị cho cả hai họ package.

Trong module Java 16, jpackage đã là công cụ đóng gói ổn định và các tùy chọn Linux này vẫn có ích trong quy trình phát hành Java hiện đại. Bài này tập trung vào metadata, desktop entry, shortcut, dependency hệ điều hành và cách kiểm tra nội dung package. Cần phân biệt dependency của package Linux với dependency Java được đóng gói trong JAR hoặc runtime image.

## 1. Metadata của DEB và RPM có vai trò gì?

DEB và RPM đều lưu metadata để hệ thống quản lý package hiểu ứng dụng là gì, phiên bản nào đang được cài, ai duy trì package và những package nào phải có trước khi cài.

| Thông tin | DEB | RPM | Mục đích |
|---|---|---|---|
| Tên package | Package | Name | Định danh ổn định để cài, nâng cấp và gỡ package. |
| Phiên bản | Version | Version | Phiên bản phát hành của ứng dụng. |
| Bản sửa đổi package | Debian revision trong Version | Release | Phân biệt lần đóng gói lại khi phiên bản ứng dụng không đổi. |
| Maintainer | Maintainer | Thông tin vendor/packager tùy metadata | Cho biết đơn vị duy trì hoặc phát hành package. |
| Dependency | Depends | Requires | Khai báo package hoặc capability cần có. |
| Phân loại | Section | Group trong spec | Metadata phân loại package theo hệ sinh thái. |
| License | Thông tin copyright/license trong package | License | Mô tả giấy phép của phần mềm được đóng gói. |

Metadata không thay thế nội dung ứng dụng. Ví dụ, **--linux-package-deps** không đóng gói thư viện vào JAR và cũng không thêm Java module vào runtime. Nó khai báo yêu cầu với package manager của hệ điều hành.

## 2. Đặt tên package ổn định bằng --linux-package-name

**--name** là tên ứng dụng dùng trong quá trình đóng gói. **--linux-package-name** đặt tên package Linux. Hai tên có thể giống nhau nhưng không bắt buộc phải giống.

Ví dụ:

~~~bash
jpackage \
  --type deb \
  --name "Inventory Desk" \
  --linux-package-name inventory-desk \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Trong ví dụ:

- Inventory Desk là tên ứng dụng hiển thị.
- inventory-desk là tên package mà công cụ quản lý gói sử dụng.
- 1.4.0 là phiên bản ứng dụng/package.

Nên giữ package name ổn định qua các bản phát hành. Nếu đổi tên package giữa hai phiên bản, hệ thống có thể xem đó là package khác, khiến nâng cấp, dependency hoặc script triển khai không còn hoạt động như mong đợi.

Đặt tên theo quy ước của hệ package đích. Với Debian, tên package thường dùng chữ thường, chữ số, dấu cộng, dấu trừ và dấu chấm theo quy tắc Debian Policy. Với RPM, kiểm tra quy tắc đặt tên của bản phân phối mục tiêu.

Nếu bỏ **--linux-package-name**, jpackage mặc định dùng tên ứng dụng. Khi tên hiển thị có khoảng trắng hoặc ký tự không phù hợp với quy ước package, nên đặt package name tường minh.

## 3. Phiên bản ứng dụng và revision của package

**--app-version** đặt phiên bản ứng dụng/package. **--linux-app-release** đặt revision của package:

- Với RPM, giá trị được dùng cho trường Release.
- Với DEB, giá trị được dùng làm Debian revision trong trường Version.

Ví dụ:

~~~bash
jpackage \
  --type deb \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --app-version 1.4.0 \
  --linux-app-release 1 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Phiên bản DEB được tạo có thể thể hiện theo dạng 1.4.0-1. Nếu cần đóng gói lại cùng phiên bản ứng dụng để sửa metadata hoặc thay đổi cách đóng gói, có thể tăng revision package theo chính sách phát hành.

Ví dụ chuỗi phát hành:

| Phiên bản ứng dụng | Package revision | Ý nghĩa |
|---|---:|---|
| 1.4.0 | 1 | Lần đóng gói đầu tiên. |
| 1.4.0 | 2 | Đóng gói lại cùng phiên bản ứng dụng. |
| 1.5.0 | 1 | Phiên bản ứng dụng mới. |

Không dùng revision package để thay thế version ứng dụng. Giữ hai khái niệm riêng giúp package manager so sánh phiên bản đúng và giúp người vận hành nhận biết bản sửa đổi đóng gói.

## 4. Khai báo maintainer cho DEB

**--linux-deb-maintainer** đặt thông tin maintainer trong metadata của gói DEB. Giá trị thường là địa chỉ email liên hệ của đơn vị duy trì package.

~~~bash
jpackage \
  --type deb \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --linux-deb-maintainer packages@example.com \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Hãy dùng địa chỉ liên hệ thực tế mà người dùng hoặc bộ phận quản trị có thể sử dụng. Không để email minh họa như packages@example.com trong package phát hành thật.

Tùy chọn này dành cho DEB. Không dùng nó để thay thế trường vendor chung hoặc trường license của RPM.

## 5. Khai báo license cho RPM

**--linux-rpm-license-type** đặt giá trị trường License trong metadata RPM. Giá trị phải mô tả giấy phép thực tế của ứng dụng và các thành phần được phân phối cùng.

Ví dụ:

~~~bash
jpackage \
  --type rpm \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --linux-rpm-license-type "Apache-2.0" \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Apache-2.0 chỉ là ví dụ. Nếu ứng dụng sử dụng giấy phép khác, hãy khai báo đúng giấy phép đó và rà soát license của thư viện đi kèm theo chính sách phân phối.

Trường License là metadata pháp lý. Nó không tự động cấp quyền sử dụng phần mềm, không thay thế file license và không chứng minh toàn bộ dependency đều tương thích với giấy phép của ứng dụng.

## 6. Phân loại package bằng --linux-app-category

**--linux-app-category** đặt thông tin phân loại package:

- Với DEB, giá trị được ghi vào trường Section của control metadata.
- Với RPM, giá trị được dùng cho trường Group trong spec.

Ví dụ với DEB:

~~~bash
jpackage \
  --type deb \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --linux-app-category utils \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

utils là ví dụ về Section của Debian. Chọn giá trị theo cách phân loại mà repository hoặc bản phân phối mục tiêu sử dụng.

Không nhầm **--linux-app-category** với **--linux-menu-group**. Section của DEB hoặc Group trong RPM là metadata package; chúng không phải cấu hình shortcut hay dependency. Trường Group của RPM chủ yếu mang tính mô tả và không nên dùng để quyết định vị trí ứng dụng trong menu desktop.

## 7. Đưa ứng dụng vào menu desktop bằng --linux-menu-group

**--linux-menu-group** xác định nhóm menu mà ứng dụng được đặt vào trong môi trường desktop Linux:

~~~bash
jpackage \
  --type deb \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --linux-menu-group Utility \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Nếu không chỉ định nhóm menu, jpackage có thể đưa ứng dụng vào nhóm Unknown trong menu do môi trường desktop/window manager cung cấp. Chọn nhóm phù hợp với chức năng ứng dụng và kiểm tra cách desktop environment hiển thị sau khi cài.

Nhóm menu là metadata dành cho trải nghiệm desktop. Nó không phải tên package, không phải dependency và cũng không thay thế **--linux-app-category**.

## 8. Tạo shortcut bằng --linux-shortcut

**--linux-shortcut** yêu cầu jpackage tạo shortcut cho ứng dụng trên Linux:

~~~bash
jpackage \
  --type deb \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --linux-shortcut \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Shortcut giúp người dùng khởi chạy ứng dụng từ giao diện desktop thay vì phải mở terminal và chạy launcher bằng tay.

Nếu cung cấp icon tùy chỉnh bằng **--icon**, jpackage trên Linux tự tạo shortcut; trong trường hợp đó không cần thêm **--linux-shortcut**. Icon phải dùng định dạng được nền tảng hỗ trợ; với resource Linux, launcher icon thường là PNG.

Nên kiểm tra shortcut sau khi cài trên desktop environment mục tiêu. Các môi trường như GNOME, KDE Plasma hoặc XFCE có thể trình bày menu và shortcut khác nhau.

## 9. Tùy chỉnh desktop entry và icon bằng --resource-dir

Ứng dụng Linux thường được tích hợp vào menu thông qua file .desktop. jpackage cung cấp **--resource-dir** để thay thế resource mặc định khi cần tùy chỉnh launcher.

Các resource Linux có thể dùng gồm:

| File resource | Vai trò |
|---|---|
| <launcher-name>.png | Icon của launcher. |
| <launcher-name>.desktop | Nội dung desktop entry dùng khi đăng ký ứng dụng vào menu. |

Ví dụ cấu trúc resource:

~~~text
packaging/
  InventoryDesk.png
  InventoryDesk.desktop
~~~

Truyền thư mục resource khi tạo package:

~~~bash
jpackage \
  --type deb \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --resource-dir packaging \
  --linux-menu-group Utility \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Tên file resource phải khớp với tên launcher mà jpackage sử dụng. Nếu có nhiều launcher, cần kiểm tra tên tương ứng của từng launcher.

Khi tự cung cấp .desktop, kiểm tra ít nhất các trường Name, Exec, Icon, Type và Categories. Exec phải trỏ đến launcher được cài; không để đường dẫn tuyệt đối trên máy build. Kiểm tra icon có tồn tại sau cài đặt và menu entry mở đúng ứng dụng.

Không chỉnh sửa file .desktop sau khi package đã được cài trên máy người dùng như một bước triển khai thủ công. Hãy đưa resource vào quy trình build để package có thể tái tạo và nâng cấp nhất quán.

## 10. Khai báo dependency hệ điều hành bằng --linux-package-deps

**--linux-package-deps** khai báo các package hoặc capability của hệ điều hành mà ứng dụng yêu cầu. Metadata này được chuyển vào thông tin dependency của DEB hoặc RPM để package manager kiểm tra khi cài đặt.

Ví dụ dependency có thể là:

- Thư viện đồ họa hệ thống mà ứng dụng JavaFX hoặc JNI cần dùng.
- Thư viện native do một dependency Java gọi qua JNI/JNA yêu cầu.
- Công cụ hoặc package hệ thống mà ứng dụng cần để thực hiện chức năng.

Tùy chọn này không đóng gói các dependency đó vào JAR và không tự tải chúng từ Internet. Package manager chỉ có thể cài hoặc xác minh dependency nếu package/capability tương ứng có trong repository hoặc nguồn package được cấu hình.

### Dependency của package khác dependency Java

| Loại dependency | Ví dụ | Cách quản lý |
|---|---|---|
| Thư viện Java | JAR của logging framework hoặc JDBC driver | Đưa vào --input hoặc dependency bundle của ứng dụng. |
| Java module | java.sql, java.desktop | Chọn runtime module qua jlink hoặc tùy chọn runtime của jpackage. |
| Runtime Java | JVM, java.base, launcher runtime | Đóng gói runtime image cùng ứng dụng hoặc quy định runtime ngoài theo thiết kế. |
| Thư viện hệ điều hành | GTK, OpenSSL, thư viện native mà ứng dụng gọi | Khai báo dependency package phù hợp bằng --linux-package-deps khi package manager cần quản lý. |

Nếu ứng dụng đã đóng gói Java runtime riêng, không khai báo một JDK/JRE của hệ thống chỉ vì ứng dụng được viết bằng Java. Chỉ khai báo các package hệ điều hành thật sự cần thiết.

### Cú pháp phụ thuộc vào định dạng package

DEB và RPM dùng quy tắc dependency khác nhau:

- DEB ghi dependency trong trường Depends của control metadata. Debian dùng danh sách package và có thể kèm ràng buộc phiên bản hoặc quan hệ thay thế.
- RPM ghi dependency trong trường Requires của spec/package metadata. RPM hỗ trợ package name, capability và ràng buộc phiên bản theo cú pháp của RPM.

Giá trị của **--linux-package-deps** là chuỗi dành cho backend đóng gói. jpackage chuyển giá trị này cho công cụ package tương ứng; không nên giả định một chuỗi dependency dùng được nguyên vẹn cho cả DEB và RPM.

Lưu ý về tài liệu phiên bản: man page JDK 16 hiển thị **--linux-package-deps** nhưng thiếu phần placeholder cho giá trị. Tài liệu jpackage hiện hành ghi rõ tham số package-dep-string. Khi dùng JDK 16, hãy kiểm tra hành vi của đúng bản JDK và smoke test package; không coi tùy chọn này là cờ boolean chỉ vì trang trợ giúp cũ bỏ sót đối số.

## 11. Ví dụ khai báo dependency cho DEB

Với DEB, dependency phải dùng tên package và cú pháp quan hệ của Debian. Ví dụ:

~~~bash
jpackage \
  --type deb \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --linux-deb-maintainer packages@example.com \
  --linux-app-category utils \
  --linux-menu-group Utility \
  --linux-package-deps "libc6 (>= 2.31), libx11-6" \
  --linux-shortcut \
  --app-version 1.4.0 \
  --linux-app-release 1 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

Đây là ví dụ minh họa cho một ứng dụng cần glibc và X11. Hãy thay tên package, phiên bản tối thiểu và dependency theo thư viện native mà ứng dụng thực sự sử dụng. Không sao chép nguyên danh sách này nếu ứng dụng không cần X11.

Kiểm tra package sau khi tạo:

~~~bash
dpkg-deb --field dist/inventory-desk_1.4.0-1_amd64.deb Package Version Section Maintainer Depends
dpkg-deb --contents dist/inventory-desk_1.4.0-1_amd64.deb
~~~

Tên file đầu ra có thể khác theo kiến trúc và quy tắc đặt tên của jpackage. Dùng đúng đường dẫn package được tạo trong thư mục dist.

## 12. Ví dụ khai báo dependency cho RPM

Với RPM, dùng tên package hoặc capability mà hệ RPM của bản phân phối mục tiêu cung cấp:

~~~bash
jpackage \
  --type rpm \
  --name InventoryDesk \
  --linux-package-name inventory-desk \
  --linux-rpm-license-type "Apache-2.0" \
  --linux-menu-group Utility \
  --linux-package-deps "gtk3 >= 3.24" \
  --linux-shortcut \
  --app-version 1.4.0 \
  --linux-app-release 1 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest dist
~~~

gtk3 >= 3.24 chỉ là ví dụ về dependency theo tên và capability của một hệ RPM. Tên package có thể khác theo bản phân phối; kiểm tra package metadata trong repository mục tiêu trước khi phát hành.

Kiểm tra metadata RPM:

~~~bash
rpm -qp --qf '%{NAME}\n%{VERSION}-%{RELEASE}\n%{LICENSE}\n%{REQUIRES}\n' dist/inventory-desk-1.4.0-1.x86_64.rpm
rpm -qpl dist/inventory-desk-1.4.0-1.x86_64.rpm
~~~

Đường dẫn và tên file là ví dụ. Dùng chính file RPM do lệnh build tạo ra.

## 13. Không khai báo dependency dư thừa hoặc sai tên

Dependency không chính xác có thể khiến người dùng không cài được package dù ứng dụng thực tế chạy được, hoặc cài thành công nhưng thiếu thư viện native lúc khởi chạy.

Một số nguyên tắc:

- Chỉ khai báo package mà ứng dụng thực sự cần tại runtime.
- Dùng tên package của đúng họ phân phối; libgtk-3-0 của Debian không nhất thiết có cùng tên trên RPM.
- Chọn phiên bản tối thiểu theo API/ABI mà ứng dụng yêu cầu, không đặt cao hơn môi trường hỗ trợ thực tế.
- Không đưa dependency Java hoặc Maven/Gradle vào trường dependency của package Linux.
- Không khai báo JDK/JRE hệ thống nếu runtime đã được đóng gói cùng ứng dụng.
- Kiểm thử trên baseline Linux thấp nhất mà sản phẩm công bố hỗ trợ.
- Kiểm tra dependency được ghi vào metadata sau khi tạo package, không chỉ đọc lệnh build.

Nếu ứng dụng hỗ trợ nhiều họ Linux, nên duy trì cấu hình dependency riêng cho DEB và RPM. Một tên package có thể tồn tại trên Debian nhưng không có trên Fedora/RHEL, hoặc có tên khác.

## 14. Kiểm tra shortcut và desktop entry sau khi cài

Tạo package thành công chưa chứng minh menu và shortcut hiển thị đúng. Hãy cài package trên desktop environment mục tiêu rồi kiểm tra:

1. Ứng dụng xuất hiện trong menu đúng nhóm.
2. Shortcut mở đúng launcher và không trỏ đến thư mục build.
3. Icon hiển thị đúng kích thước và định dạng.
4. Tên ứng dụng và mô tả hiển thị đúng.
5. Ứng dụng khởi chạy được từ menu và từ terminal.
6. Gỡ cài đặt package loại bỏ desktop entry/shortcut do package tạo.

Có thể giải nén DEB để xem nội dung:

~~~bash
mkdir -p inspect-deb
dpkg-deb --extract dist/inventory-desk_1.4.0-1_amd64.deb inspect-deb
find inspect-deb -name '*.desktop' -o -name '*.png'
~~~

Với RPM, xem danh sách file được cài:

~~~bash
rpm -qpl dist/inventory-desk-1.4.0-1.x86_64.rpm
~~~

Nếu có .desktop tùy chỉnh, mở file trong package và xác nhận Exec trỏ đến launcher cài đặt, Icon trỏ đến icon được đóng gói, Categories phù hợp với desktop menu.

## 15. Kiểm thử dependency trong môi trường sạch

Không chỉ chạy package trên máy build đã cài sẵn mọi thư viện. Hãy kiểm tra trong máy ảo hoặc môi trường tương đương với hệ điều hành đích:

1. Cài package trên hệ thống sạch có repository được cấu hình.
2. Xác nhận package manager giải quyết dependency đã khai báo.
3. Xác nhận không có dependency không cần thiết bị kéo vào.
4. Khởi chạy ứng dụng và thực hiện các chức năng có dùng native library.
5. Kiểm tra trường hợp dependency thiếu hoặc version thấp hơn mức yêu cầu.
6. Nâng cấp từ phiên bản trước và kiểm tra metadata mới.
7. Gỡ cài đặt và xác nhận package manager dọn file chương trình/shortcut đúng.
8. Lặp lại với từng bản phân phối và kiến trúc được công bố hỗ trợ.

Với DEB, có thể dùng apt install ./package.deb trên môi trường thử nghiệm để xác minh dependency. Với RPM, dùng dnf install ./package.rpm trên hệ RPM tương ứng. Không dùng dpkg -i hoặc rpm -i như bằng chứng duy nhất về khả năng tự giải quyết dependency; các lệnh này có cách xử lý dependency khác với workflow của package manager cấp cao.

## 16. Bảng tổng hợp tùy chọn Linux

| Tùy chọn | Metadata hoặc hành vi | Phạm vi |
|---|---|---|
| **--linux-package-name** | Tên package | DEB và RPM |
| **--linux-deb-maintainer** | Maintainer email | DEB |
| **--linux-menu-group** | Nhóm menu desktop | DEB và RPM |
| **--linux-package-deps** | Package/capability hệ điều hành cần có | DEB và RPM; chuỗi phụ thuộc backend |
| **--linux-rpm-license-type** | Trường License trong RPM | RPM |
| **--linux-app-release** | RPM Release hoặc Debian revision | DEB và RPM |
| **--linux-app-category** | DEB Section hoặc RPM Group metadata | DEB và RPM |
| **--linux-shortcut** | Tạo shortcut ứng dụng | DEB và RPM |
| **--icon** | Icon ứng dụng; icon Linux tùy chỉnh cũng tạo shortcut | DEB và RPM |
| **--resource-dir** | Thay resource .desktop và icon theo launcher | Linux |

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Package name không phù hợp với repository | Dùng tên hiển thị có khoảng trắng hoặc ký tự không hợp lệ | Đặt tên package ổn định bằng **--linux-package-name**. |
| Package không cài được vì dependency | Sai tên package hoặc ràng buộc phiên bản quá cao | Kiểm tra repository và metadata Depends/Requires của hệ đích. |
| Ứng dụng cài được nhưng lỗi khi chạy | Thiếu thư viện native chưa khai báo | Xác định thư viện hệ thống cần thiết và thêm dependency đúng cho DEB/RPM. |
| DEB đúng nhưng RPM sai dependency | Dùng cùng chuỗi tên package cho hai họ phân phối | Duy trì dependency riêng theo backend. |
| Ứng dụng nằm trong nhóm Unknown | Không chỉ định **--linux-menu-group** | Chọn nhóm menu phù hợp và kiểm tra trên desktop environment đích. |
| Không có shortcut trên desktop | Thiếu **--linux-shortcut** và không có icon tùy chỉnh | Thêm **--linux-shortcut** hoặc cung cấp **--icon**. |
| Icon không hiển thị | Sai định dạng, tên resource hoặc đường dẫn trong desktop entry | Dùng icon đúng định dạng, kiểm tra resource và file .desktop. |
| Package metadata không phản ánh version mong muốn | Nhầm **--app-version** với **--linux-app-release** | Đặt version ứng dụng và revision package riêng. |
| License RPM không đúng | Dùng giá trị minh họa hoặc tên giấy phép không khớp | Khai báo license thực tế bằng **--linux-rpm-license-type**. |

## 18. Quy trình phát hành DEB/RPM đề xuất

1. Xác định các bản phân phối Linux và kiến trúc CPU được hỗ trợ.
2. Chọn package name ổn định cho sản phẩm.
3. Xác định version ứng dụng và revision package.
4. Khai báo maintainer cho DEB và license cho RPM.
5. Chọn nhóm menu, icon và shortcut phù hợp.
6. Phân tích dependency native thực tế; tạo danh sách riêng cho DEB và RPM.
7. Dùng jpackage trên nền tảng Linux phù hợp để tạo từng package.
8. Kiểm tra metadata bằng dpkg-deb hoặc rpm.
9. Cài thử trên hệ thống sạch, xác nhận dependency, menu, shortcut và launcher.
10. Lưu package, checksum, phiên bản JDK, cấu hình build và kết quả kiểm thử.

## 19. Cách áp dụng trong quy trình Java hiện đại

- Dùng **--linux-package-name** cho định danh package ổn định, tách khỏi tên hiển thị.
- Quản lý **--app-version** và **--linux-app-release** như hai thành phần version khác nhau.
- Dùng **--linux-deb-maintainer** cho DEB và **--linux-rpm-license-type** cho RPM.
- Dùng **--linux-menu-group** để phân loại menu desktop; dùng **--linux-shortcut** hoặc icon tùy chỉnh để tạo lối mở ứng dụng.
- Dùng **--linux-app-category** cho metadata Section/Group khi repository mục tiêu cần trường đó; không dùng nó thay cho menu group.
- Chỉ khai báo dependency hệ điều hành thật sự cần bằng **--linux-package-deps**.
- Tạo cấu hình dependency riêng cho DEB và RPM vì tên package và cú pháp khác nhau.
- Phân biệt package dependency với Java library, Java module và runtime image.
- Kiểm tra metadata, .desktop, icon, shortcut và dependency trên môi trường Linux sạch trước khi phát hành.

Metadata và dependency Linux quyết định cách package manager nhận diện, cài đặt và quản lý ứng dụng; menu group và shortcut quyết định cách người dùng tìm thấy ứng dụng trên desktop. Dùng đúng tùy chọn cho DEB/RPM, khai báo dependency native tối thiểu và kiểm tra package sau khi tạo giúp ứng dụng Java được phân phối ổn định trên các bản Linux mục tiêu.

## Tài liệu tham khảo

- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle JDK 16 — Packaging Overview](https://docs.oracle.com/en/java/javase/16/jpackage/packaging-overview.html)
- [Oracle JDK 24 — Manage the Installation of Your Application](https://docs.oracle.com/en/java/javase/24/jpackage/manage-installation.html)
- [Oracle JDK 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Debian Policy Manual — Declaring Relationships Between Packages](https://www.debian.org/doc/debian-policy/ch-relationships.html)
- [OpenJDK — Correct documentation for --linux-package-deps](https://git.openjdk.org/jdk/pull/23638)
