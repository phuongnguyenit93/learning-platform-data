# Thiết lập --name, --app-version, --vendor và --description

`jpackage` là công cụ đóng gói ứng dụng Java thành application image hoặc gói cài đặt native. Từ Java 16, công cụ này trở thành tính năng production-ready theo JEP 392. Bốn tùy chọn `--name`, `--app-version`, `--vendor` và `--description` cung cấp thông tin nhận diện ứng dụng trong quá trình đóng gói.

Các giá trị này giúp người dùng và công cụ quản lý phần mềm nhận biết tên sản phẩm, phiên bản và nhà cung cấp. Chúng không sửa mã nguồn, manifest của JAR hoặc version của dependency. Muốn thông tin phát hành nhất quán, hãy quản lý version trong quy trình build rồi truyền cùng giá trị vào `jpackage`.

## 1. Metadata ứng dụng trong jpackage

`jpackage` nhận ứng dụng Java đã build cùng tài nguyên cần thiết, sau đó tạo application image có runtime đi kèm hoặc gói cài đặt native theo nền tảng. Metadata là thông tin mô tả ứng dụng, ví dụ tên sản phẩm, phiên bản phát hành, đơn vị phát hành và mô tả ngắn.

| Tùy chọn | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `--name` hoặc `-n` | Tên ứng dụng và/hoặc package | Tên main JAR hoặc module nếu không chỉ định |
| `--app-version` | Phiên bản ứng dụng và/hoặc package | `1.0` |
| `--vendor` | Nhà cung cấp/đơn vị phát hành | Không có |
| `--description` | Mô tả ứng dụng | Không có |

Đây là generic options của `jpackage` trong Java 16. Cách chúng được lưu và hiển thị phụ thuộc loại package và nền tảng. Không phải application image nào cũng trình bày metadata giống installer native.

## 2. Chuẩn bị đầu vào

Ví dụ trong bài dùng ứng dụng không modular:

```text
project/
  build/
    package-input/
      inventory-desktop.jar
      lib/
        database-driver.jar
```

Thư mục truyền cho `--input` chứa main JAR và các thư viện cần đóng gói. Giá trị của `--main-jar` là tên file JAR tương đối với thư mục input. Nếu manifest chưa khai báo main class, truyền thêm `--main-class`.

Kiểm tra công cụ và option của JDK đang dùng:

```bash
jpackage --version
jpackage --help
```

Từ Java 16, module của công cụ là `jdk.jpackage`. `jpackage` từng là công cụ incubator trong JDK 14 và 15; từ JDK 16, đây là công cụ production-ready theo JEP 392.

## 3. Thiết lập --name

`--name` đặt tên ứng dụng và/hoặc package. Tên này thường được dùng cho tên application image, launcher chính và tên package được tạo.

```bash
jpackage --type app-image --input build/package-input --name "Inventory Desk" --main-jar inventory-desktop.jar --main-class vn.example.inventory.Main --dest build/package-output
```

Nếu không truyền `--name`, `jpackage` dùng tên main JAR hoặc module làm mặc định. Tên file JAR nội bộ vì thế không nhất thiết phải là tên sản phẩm người dùng nhìn thấy.

Nên chọn tên dễ đọc, nhất quán giữa tài liệu, installer và launcher. Tránh nhúng version vào tên nếu version đã được quản lý bằng `--app-version`.

Một số nền tảng có option riêng cho tên ở một ngữ cảnh cụ thể. Linux có `--linux-package-name` để đặt tên package khác; macOS có `--mac-package-name` cho tên hiển thị trong menu bar. Các option đó phục vụ mục đích riêng và không thay thế vai trò chung của `--name`.

## 4. Thiết lập --app-version

`--app-version` xác định phiên bản ứng dụng và/hoặc package:

```bash
jpackage --type app-image --input build/package-input --name "Inventory Desk" --app-version 2.4.1 --main-jar inventory-desktop.jar --main-class vn.example.inventory.Main --dest build/package-output
```

Nếu không truyền option này, version mặc định là `1.0`. Version thường tham gia vào tên package được tạo, ví dụ dạng `Inventory Desk-2.4.1` trước phần mở rộng tùy loại installer.

Nên dùng quy ước version nhất quán, chẳng hạn `2.4.1`, `2.5.0` và `3.0.0`. Đây là quy ước phát hành do nhóm phát triển chọn, không phải cú pháp bắt buộc của `jpackage`. Native package format và công cụ đóng gói phía dưới có thể áp đặt quy tắc riêng cho trường version. Dạng số phân tách bằng dấu chấm thường dễ tương thích; hãy kiểm tra trên nền tảng đích nếu cần hậu tố pre-release hoặc metadata phức tạp.

### --app-version không cập nhật version trong JAR

`--app-version` mô tả version của application/package được tạo. Nó không sửa:

- `Implementation-Version` trong `MANIFEST.MF`.
- Version artifact do Maven hoặc Gradle quản lý.
- Version thư viện dependency.
- Hằng số hoặc trang About viết bên trong ứng dụng.

Nếu sản phẩm hiển thị version trong giao diện, hãy cấp cùng một giá trị từ quy trình build cho cả metadata đóng gói và thông tin mà ứng dụng sử dụng. Tránh để installer báo 2.4.1 nhưng màn hình About lại hiển thị 2.3.0.

## 5. Thiết lập --vendor

`--vendor` ghi tên nhà cung cấp hoặc đơn vị phát hành ứng dụng:

```bash
jpackage --type app-image --input build/package-input --name "Inventory Desk" --app-version 2.4.1 --vendor "Example Software Ltd." --main-jar inventory-desktop.jar --main-class vn.example.inventory.Main --dest build/package-output
```

Không có vendor mặc định. Nếu package cần nhận diện đơn vị phát hành, hãy truyền giá trị rõ ràng.

Tên vendor nên nhất quán giữa các bản phát hành, dùng tên pháp lý hoặc thương hiệu của đơn vị phát hành và không chứa thông tin nội bộ cần giữ kín.

`--vendor` chỉ là metadata văn bản do nhà phát triển cung cấp. Nó không ký số package, không xác minh doanh nghiệp và không tự tạo trạng thái publisher đáng tin cậy trên hệ điều hành. Nếu cần ký installer hoặc bundle, phải cấu hình quy trình ký riêng theo nền tảng.

## 6. Thiết lập --description

`--description` đặt mô tả ngắn cho ứng dụng:

```bash
jpackage --type app-image --input build/package-input --name "Inventory Desk" --app-version 2.4.1 --vendor "Example Software Ltd." --description "Desktop application for inventory management" --main-jar inventory-desktop.jar --main-class vn.example.inventory.Main --dest build/package-output
```

Không có mô tả mặc định. Giá trị có dấu cách cần được đặt trong dấu nháy để shell truyền thành một tham số duy nhất.

Mô tả tốt nên nêu chức năng chính, ngắn gọn và dễ hiểu với người cài đặt. Ví dụ:

```text
Desktop application for inventory management
Tool for viewing and exporting operational reports
Client application for connecting to the company service
```

`--description` là metadata package. Nó không tự tạo README, trang giới thiệu, tài liệu trợ giúp hoặc nội dung About bên trong ứng dụng. Các nội dung đó cần được cung cấp như tài nguyên riêng.

## 7. Kết hợp cả bốn tùy chọn

Ví dụ đóng gói application image cho ứng dụng không modular:

```bash
jpackage --type app-image --input build/package-input --name "Inventory Desk" --app-version 2.4.1 --vendor "Example Software Ltd." --description "Desktop application for inventory management" --main-jar inventory-desktop.jar --main-class vn.example.inventory.Main --dest build/package-output
```

Lệnh này đọc các file trong `build/package-input`, dùng `inventory-desktop.jar` làm main JAR, chạy lớp `vn.example.inventory.Main`, đặt tên ứng dụng, version, vendor và description, rồi ghi application image vào `build/package-output`.

`--type app-image` tạo application image để kiểm tra hoặc phân phối theo cách phù hợp. Nó không tạo installer native như MSI hay DEB.

## 8. Tạo installer native với cùng metadata

Sau khi kiểm tra application image, có thể tạo package cài đặt trên nền tảng đích. Ví dụ trên Windows:

```powershell
jpackage --type msi --input build/package-input --name "Inventory Desk" --app-version 2.4.1 --vendor "Example Software Ltd." --description "Desktop application for inventory management" --main-jar inventory-desktop.jar --main-class vn.example.inventory.Main --dest build/packages
```

Trên Linux, chọn `deb` hoặc `rpm` theo hệ phân phối. Trên macOS, có thể tạo `dmg` hoặc `pkg` theo mục đích phân phối.

Native package phải được build trên nền tảng tương ứng. `jpackage` không cung cấp cross-package để tạo installer Windows từ macOS hoặc installer Linux từ Windows. Công cụ cũng cần phần mềm phụ trợ theo nền tảng; Java 16 yêu cầu WiX trên Windows để tạo EXE/MSI.

Dùng cùng metadata cho các bản build của cùng một phát hành để tên sản phẩm, version và vendor nhất quán. Giao diện hiển thị metadata của Windows Installer, package manager Linux và bundle macOS có thể khác nhau.

## 9. Metadata được sử dụng ở đâu?

Mục đích chung của bốn option không đồng nghĩa chúng xuất hiện ở cùng một vị trí trên mọi hệ điều hành.

| Metadata | Vai trò phổ biến |
|---|---|
| Name | Tên application image, launcher và package |
| App version | Phiên bản ứng dụng/package và thành phần tên package |
| Vendor | Nhà cung cấp được ghi trong metadata package khi định dạng hỗ trợ |
| Description | Mô tả package khi định dạng hỗ trợ |

Tài liệu đóng gói Java 16 minh họa việc thiết lập name, version, description và vendor trên Windows. Khi chuyển sang Linux hoặc macOS, hãy kiểm tra metadata package tạo ra và cách trình quản lý phần mềm của nền tảng hiển thị nó.

Không suy luận rằng chuỗi truyền thành công trên command line chắc chắn xuất hiện trong mọi màn hình hệ điều hành. Application image và installer native có mục đích khác nhau; package manager cũng có cách biểu diễn metadata riêng.

## 10. Phân biệt name với tên riêng theo nền tảng

`--name` là tên chung của ứng dụng/package. Một số nền tảng có option bổ sung cho định danh hoặc tên hiển thị riêng:

| Nền tảng | Option | Vai trò |
|---|---|---|
| Linux | `--linux-package-name` | Tên package Linux |
| macOS | `--mac-package-name` | Tên ứng dụng hiển thị trong menu bar |
| macOS | `--mac-package-identifier` | Định danh duy nhất của ứng dụng |

Ví dụ macOS:

```bash
jpackage --type dmg --input build/package-input --name "Inventory Desk" --mac-package-name "Inventory" --mac-package-identifier "com.example.inventory" --app-version 2.4.1 --vendor "Example Software Ltd." --description "Desktop application for inventory management" --main-jar inventory-desktop.jar --main-class vn.example.inventory.Main --dest build/packages
```

`--mac-package-name` có giới hạn độ dài và mục đích hiển thị riêng theo tài liệu Java 16. `--mac-package-identifier` có quy tắc ký tự riêng. Không dùng các option nền tảng trên hệ điều hành không hỗ trợ chúng.

## 11. Quoting và ký tự đặc biệt trong metadata

Các giá trị chứa dấu cách phải được truyền thành một tham số:

```bash
jpackage --name "Inventory Desk" --vendor "Example Software Ltd." --description "Desktop application for inventory management" ...
```

Trong PowerShell, dấu nháy kép cũng gom phần có dấu cách thành một đối số. Với mô tả có dấu nháy kép bên trong, escape theo quy tắc shell đang sử dụng.

Ví dụ Bash:

```bash
jpackage --description "Inventory manager for North warehouse" ...
```

Ví dụ PowerShell:

```powershell
jpackage --description 'Inventory manager for "North" warehouse' ...
```

Nội dung Unicode như tiếng Việt có thể được truyền trong metadata, nhưng cần kiểm tra encoding của terminal, script build và backend package. Nếu package được tạo trên nhiều hệ điều hành, hãy xác minh ký tự tiếng Việt hiển thị đúng trong metadata từng định dạng.

Không đưa ký tự xuống dòng hoặc nội dung nhiều đoạn vào description nếu chưa kiểm tra cách package backend xử lý. Mô tả ngắn một dòng dễ kiểm soát hơn.

## 12. Quản lý metadata tập trung trong quy trình build

Không nên sao chép name, version, vendor và description tùy tiện vào nhiều lệnh phát hành. Hãy quản lý chúng từ một nguồn cấu hình của dự án hoặc pipeline.

Ví dụ file cấu hình release ở mức khái niệm:

```text
APP_NAME=Inventory Desk
APP_VERSION=2.4.1
APP_VENDOR=Example Software Ltd.
APP_DESCRIPTION=Desktop application for inventory management
```

Pipeline có thể đọc các giá trị này rồi truyền vào `jpackage`. Cách triển khai phụ thuộc build tool và CI đang dùng.

Các lợi ích:

- Build Windows, Linux và macOS dùng cùng một version.
- Vendor và tên sản phẩm không bị sai khác giữa các installer.
- Có thể rà soát thay đổi metadata trong lịch sử source control.
- Quy trình phát hành dễ tái lập.
- Giảm lỗi nhập tay giữa các lệnh.

Không lưu secret ký số, mật khẩu hoặc private key trong file metadata. Các option trong bài chỉ dành cho thông tin mô tả package.

## 13. Kiểm tra metadata sau khi đóng gói

Sau khi chạy `jpackage`, hãy xác minh artifact được tạo và metadata theo định dạng đích.

Quy trình kiểm tra:

1. Xác nhận application image hoặc installer xuất hiện trong thư mục `--dest`.
2. Kiểm tra tên thư mục, launcher hoặc file package theo `--name` và `--app-version`.
3. Dùng công cụ của hệ điều hành để xem metadata package nếu định dạng hỗ trợ.
4. Kiểm tra vendor và description có được ghi đúng hay không.
5. Cài thử package trên môi trường sạch của nền tảng đích.
6. Khởi chạy ứng dụng và kiểm tra tên hiển thị, chức năng và runtime đi kèm.
7. Lưu artifact và lệnh build để có thể tái tạo bản phát hành.

Đối với application image, kiểm tra cấu trúc thư mục, launcher, file cấu hình và runtime. Với installer native, kiểm tra metadata bằng công cụ tương ứng của hệ điều hành hoặc package manager.

Tên file đầu ra không đủ để chứng minh toàn bộ metadata đã được ghi chính xác. Vendor và description cần được xác minh trong package metadata nếu đó là yêu cầu phát hành.

## 14. Lỗi thường gặp

**Bỏ qua `--name` rồi ngạc nhiên khi tên sản phẩm là tên JAR.** Nếu không chỉ định, jpackage dùng tên main JAR hoặc module. Hãy đặt tên sản phẩm rõ ràng.

**Nhúng version vào `--name`.** Việc này khiến tên launcher và application image thay đổi theo mỗi bản phát hành. Quản lý version bằng `--app-version`.

**Cho rằng `--app-version` cập nhật manifest của JAR.** Option chỉ đặt version cho application/package được tạo. Cập nhật metadata bên trong JAR cần thực hiện ở bước build ứng dụng.

**Không truyền vendor và description nhưng mong hệ điều hành tự suy ra.** Hai option này không có giá trị mặc định. Hãy cung cấp nếu package cần hiển thị thông tin đó.

**Coi vendor là chữ ký số.** Vendor là metadata văn bản. Muốn xác thực publisher và bảo vệ tính toàn vẹn package, cần quy trình ký số riêng.

**Dùng `--name` để thay mọi tên riêng theo nền tảng.** Linux và macOS có option riêng cho package name, menu bar name hoặc application identifier.

**Không đặt dấu nháy cho giá trị có dấu cách.** Shell có thể tách một metadata thành nhiều đối số. Bao chuỗi bằng dấu nháy phù hợp.

**Giả định metadata hiển thị giống nhau trên app-image và installer.** Application image không phải installer native. Kiểm tra artifact và package metadata theo định dạng cụ thể.

**Dùng một bộ build để tạo package cho mọi hệ điều hành.** jpackage cần chạy trên nền tảng đích và có thể yêu cầu công cụ đóng gói riêng.

**Không kiểm tra version với package backend.** Một version hợp lệ theo quy ước dự án chưa chắc hợp lệ với mọi native package format. Dùng quy ước dễ tương thích và kiểm thử trên nền tảng đích.

## 15. Ghi nhớ

- `jpackage` trở thành công cụ production-ready từ Java 16 theo JEP 392.
- `--name` đặt tên ứng dụng và/hoặc package; mặc định dựa trên tên main JAR hoặc module.
- `--app-version` đặt phiên bản ứng dụng/package; mặc định là `1.0`.
- `--vendor` xác định nhà cung cấp và không có mặc định.
- `--description` mô tả ứng dụng và không có mặc định.
- Giá trị có dấu cách phải được quote theo shell.
- `--app-version` không sửa manifest hoặc version của dependency.
- `--vendor` không thay thế ký số package hoặc xác minh publisher.
- Metadata được thể hiện khác nhau tùy application image, installer và hệ điều hành.
- `--linux-package-name`, `--mac-package-name` và `--mac-package-identifier` có vai trò nền tảng riêng.
- Native installer phải được tạo trên nền tảng đích và cần công cụ phụ trợ tương ứng.
- Kiểm tra metadata trong artifact thực tế sau khi đóng gói.

Khi quản lý bốn metadata option nhất quán, nhóm phát triển có thể tạo application image và installer dễ nhận biết, theo dõi version rõ ràng và cung cấp thông tin phát hành đáng tin cậy cho người dùng. Hãy xem các giá trị này là một phần của quy trình release và xác minh chúng trên package native mà người dùng sẽ cài đặt.

## Tài liệu tham khảo

- [JEP 392 – Packaging Tool](https://openjdk.org/jeps/392) — đưa jpackage thành công cụ production-ready trong Java 16.
- [The jpackage Command – Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html) — option name, app-version, vendor, description và cú pháp công cụ.
- [Packaging Tool User's Guide – Java SE 16](https://docs.oracle.com/en/java/javase/16/jpackage/) — chuẩn bị ứng dụng, application image và native package.
- [Basic Packaging – Java SE 24](https://docs.oracle.com/en/java/javase/24/jpackage/basic-packaging.html) — ví dụ metadata và hành vi mặc định trong tài liệu hiện đại.

