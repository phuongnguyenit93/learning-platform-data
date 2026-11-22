# Version package với jpackage

`jpackage` là công cụ của JDK dùng để đóng gói ứng dụng Java thành application image hoặc bộ cài native cho Windows, Linux và macOS. Khi phát hành nhiều phiên bản, cần đặt version package rõ ràng để người dùng nhận biết bản đang cài, hệ điều hành quản lý việc nâng cấp và nhóm phát triển phân biệt các lần phát hành.

Tùy chọn trung tâm là `--app-version`. Tuy nhiên, version của ứng dụng, revision của gói Linux và mã nhận diện dòng sản phẩm trên Windows/macOS là những thông tin khác nhau. Hiểu đúng từng giá trị giúp tránh đặt nhầm version hoặc làm hỏng luồng nâng cấp.

Bài học dùng cú pháp JDK 21 làm mốc.

## 1. Phân biệt các loại version

| Giá trị | Ý nghĩa | Công cụ/tùy chọn |
|---|---|---|
| Version của ứng dụng/package | Phiên bản sản phẩm được đóng gói, ví dụ `2.4.1` | `jpackage --app-version` |
| Version của công cụ | Phiên bản chương trình `jpackage` trong JDK đang chạy | `jpackage --version` |
| Revision của package Linux | Lần sửa đổi cách đóng gói RPM/DEB, ví dụ `2` | `--linux-app-release` |
| Upgrade identity của Windows | UUID nhận diện nhóm sản phẩm liên quan để Windows Installer xét nâng cấp | `--win-upgrade-uuid` |
| Application identifier của macOS | Định danh ổn định của ứng dụng trong hệ sinh thái macOS | `--mac-package-identifier` |
| Version trong mã nguồn/build | Version do Maven, Gradle, manifest hoặc ứng dụng tự quản lý | Cấu hình build/metadata riêng |

Các giá trị này không thay thế lẫn nhau. Ví dụ, đổi `--app-version` từ `2.4.1` thành `2.4.2` không có nghĩa là phải đổi UUID nâng cấp của Windows hoặc application identifier của macOS.

## 2. Dùng --app-version

Cú pháp:

~~~text
jpackage --app-version version [other-options]
~~~

`--app-version` xác định version của ứng dụng và/hoặc package. Nếu không chỉ định, JDK 21 mặc định version là `1.0`.

Ví dụ:

~~~bash
jpackage --name DynamicTreeDemo \
  --app-version 2.0 \
  --input myApps \
  --main-jar DynamicTree.jar
~~~

Trong ví dụ:

- `--name DynamicTreeDemo` đặt tên ứng dụng/package.
- `--app-version 2.0` đặt version sản phẩm.
- `--input myApps` chỉ định thư mục chứa nội dung ứng dụng.
- `--main-jar DynamicTree.jar` chọn JAR chính.

Tên package được tạo từ tên ứng dụng và version. Tài liệu Oracle minh họa kết quả là `DynamicTreeDemo-2.0.exe` khi tạo package Windows.

### 2.1. Version mặc định

Nếu chạy:

~~~bash
jpackage --name VersionDemo \
  --input input \
  --main-jar VersionDemo.jar
~~~

và không cung cấp `--app-version`, package sử dụng version mặc định `1.0`.

Khi muốn phát hành bản mới, hãy chỉ định version rõ ràng:

~~~bash
jpackage --name VersionDemo \
  --app-version 2.4.1 \
  --input input \
  --main-jar VersionDemo.jar
~~~

Không nên phụ thuộc vào version mặc định trong pipeline phát hành vì tên artifact và metadata package có thể không phản ánh version thực tế của sản phẩm.

### 2.2. --version khác --app-version

Hai tùy chọn có mục đích hoàn toàn khác nhau:

~~~bash
jpackage --version
~~~

Lệnh này in version của công cụ `jpackage` rồi kết thúc.

~~~bash
jpackage --app-version 2.4.1 --help
~~~

`--app-version` là metadata sản phẩm được dùng khi tạo package; nó không thay đổi version JDK hoặc version của công cụ.

Khi kiểm tra build, có thể ghi nhận cả hai:

~~~bash
java --version
jpackage --version
~~~

Nhờ vậy, log CI cho biết JDK/toolchain nào đã tạo artifact và version sản phẩm nào được yêu cầu.

## 3. Chọn quy ước version cho ứng dụng

Một quy ước phổ biến là `MAJOR.MINOR.PATCH`:

| Phần | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| MAJOR | Thay đổi lớn hoặc không tương thích | `3.0.0` |
| MINOR | Bổ sung chức năng tương thích ngược | `2.5.0` |
| PATCH | Sửa lỗi tương thích ngược | `2.4.2` |

Đây là quy ước quản lý phát hành của dự án, không phải thuật toán tự động do `jpackage` áp đặt.

Ví dụ một chuỗi phát hành:

- `2.4.0`: bản phát hành tính năng.
- `2.4.1`: bản sửa lỗi.
- `2.5.0`: bổ sung tính năng tương thích.
- `3.0.0`: bản thay đổi lớn.

Nên chọn một nguồn version duy nhất trong cấu hình build rồi truyền giá trị đó vào lệnh `jpackage`. Không nên để version trong Maven/Gradle là `2.4.2` nhưng package lại mang version `2.3.0`.

### 3.1. Version có hậu tố

Các dự án có thể dùng version thử nghiệm như `2.5.0-rc.1` hoặc metadata build như `2.5.0+build.12`.

Tuy nhiên, định dạng version của package còn phụ thuộc hệ điều hành và công cụ đóng gói native. Không nên giả định mọi hậu tố SemVer đều được Windows Installer, RPM, DEB và macOS chấp nhận giống nhau.

Để có giá trị dùng chung giữa các nền tảng, có thể dùng version số dạng `2.5.0` cho `--app-version`, còn thông tin release candidate, commit hoặc build number được ghi riêng trong metadata của ứng dụng hoặc hệ thống phát hành. Nếu cần dùng hậu tố trực tiếp trong package version, hãy kiểm tra trên từng nền tảng đích.

## 4. Version ứng dụng và tên package

Một số tùy chọn liên quan:

| Tùy chọn | Vai trò |
|---|---|
| `--name` | Tên ứng dụng và package |
| `--app-version` | Version ứng dụng/package |
| `--vendor` | Tên nhà cung cấp |
| `--description` | Mô tả ứng dụng |
| `--copyright` | Thông tin bản quyền |
| `--dest` | Thư mục chứa artifact đầu ra |
| `--type` | Loại package cần tạo |
| `--linux-package-name` | Tên package trên Linux |

Ví dụ:

~~~bash
jpackage --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --vendor "Example Studio" \
  --description "Versioning demonstration application" \
  --copyright "Copyright 2026 Example Studio" \
  --dest dist
~~~

Lệnh tạo application image chứa launcher, ứng dụng và runtime image. Có thể dùng application image để thử trước khi tạo bộ cài native.

Các loại package thường gặp:

| Nền tảng | Loại package |
|---|---|
| Windows | `exe`, `msi` |
| Linux | `deb`, `rpm` |
| macOS | `pkg`, `dmg` |
| Application image | `app-image` |

Package native phải được tạo trên nền tảng đích. Muốn phát hành cho nhiều hệ điều hành, cần chạy quy trình đóng gói trên từng hệ điều hành tương ứng.

## 5. Version và revision trên Linux

Linux package manager thường phân biệt version của phần mềm với revision của gói phân phối.

Trong `jpackage`, tùy chọn:

~~~text
--linux-app-release release
~~~

được dùng làm:

- Giá trị Release trong RPM spec.
- Debian revision trong DEB control file.

Ví dụ:

~~~bash
jpackage --type deb \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --linux-app-release 2 \
  --linux-package-name versiondemo \
  --dest dist
~~~

Ở đây:

- `2.4.1` là version ứng dụng.
- `2` là revision của package Linux.
- `versiondemo` là tên package Linux.

### 5.1. Khi nào tăng linux-app-release?

Giả sử ứng dụng vẫn ở version `2.4.1`, nhưng nhóm phát triển cần tạo lại package do thay đổi script cài đặt hoặc metadata đóng gói.

Có thể phát hành:

| Lần đóng gói | Application version | Linux package release |
|---|---|---|
| Lần đầu | `2.4.1` | `1` |
| Sửa package script | `2.4.1` | `2` |
| Có bản sửa lỗi ứng dụng | `2.4.2` | `1` |

Bảng trên là ví dụ quy ước quản lý của dự án. Hãy tuân theo chính sách version/revision của repository DEB hoặc RPM mà sản phẩm phát hành.

Không dùng `--linux-app-release` để thay thế version sản phẩm. Nếu phần mềm thực sự chuyển từ `2.4.1` sang `2.4.2`, cần cập nhật `--app-version`.

## 6. Version và nâng cấp trên Windows

Windows package có thể dùng EXE hoặc MSI. Tùy chọn liên quan đến dòng nâng cấp là:

~~~text
--win-upgrade-uuid id
~~~

Đây là UUID gắn với việc nâng cấp package. Trong Windows Installer, UpgradeCode được dùng để nhận diện một nhóm sản phẩm liên quan qua các phiên bản.

Ví dụ:

~~~powershell
jpackage --type msi `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version 2.4.1 `
  --vendor "Example Studio" `
  --win-upgrade-uuid "12345678-1234-5678-9abc-def012345678" `
  --dest dist
~~~

Khi phát hành bản `2.4.2` của cùng sản phẩm, thường giữ nguyên UUID nâng cấp:

~~~powershell
jpackage --type msi `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version 2.4.2 `
  --vendor "Example Studio" `
  --win-upgrade-uuid "12345678-1234-5678-9abc-def012345678" `
  --dest dist
~~~

Các nguyên tắc:

- Giữ UUID ổn định cho cùng một dòng sản phẩm cần được Windows Installer nhận diện là các phiên bản liên quan.
- Dùng UUID khác khi tạo một sản phẩm hoặc product family độc lập.
- Tăng `--app-version` khi phát hành version ứng dụng mới.
- Không tạo UUID ngẫu nhiên khác nhau cho từng bản cập nhật nếu muốn duy trì cùng nhóm nâng cấp.

UUID nâng cấp là thông tin nhận diện quan hệ sản phẩm. Nó không phải version, không phải tên file và không tự bảo đảm mọi tình huống nâng cấp đều thành công. Cần kiểm tra hành vi cài mới, cập nhật và gỡ cài đặt bằng đúng bộ MSI/EXE mà sản phẩm phát hành.

## 7. Version và định danh trên macOS

Trên macOS, `jpackage` hỗ trợ package `pkg` và `dmg`.

Tùy chọn:

~~~text
--mac-package-identifier identifier
~~~

đặt định danh duy nhất cho ứng dụng. Nếu không chỉ định, giá trị mặc định dựa trên tên main class.

Ví dụ:

~~~bash
jpackage --type pkg \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --mac-package-identifier com.example.versiondemo \
  --dest dist
~~~

Nên dùng định danh ổn định theo dạng reverse-DNS, ví dụ `com.example.versiondemo`, và giữ nguyên qua các lần phát hành của cùng ứng dụng.

Phân biệt:

- `--app-version 2.4.1`: version sản phẩm.
- `--mac-package-identifier com.example.versiondemo`: danh tính ứng dụng trên macOS.
- `--name VersionDemo`: tên ứng dụng hiển thị/đóng gói.

Không thay đổi identifier chỉ vì ứng dụng được nâng từ `2.4.1` lên `2.4.2`. Identifier mới có thể khiến hệ điều hành hoặc công cụ quản lý xem ứng dụng như một sản phẩm khác.

## 8. Version package không tự cập nhật version trong source code

`--app-version` đặt version cho quá trình đóng gói. Không nên xem nó là lệnh cập nhật tất cả các version khác trong dự án.

Một dự án có thể có nhiều nơi lưu version:

- Version trong Maven `pom.xml`.
- Version trong Gradle build file.
- Version trong tên JAR.
- Version trong manifest hoặc resource của ứng dụng.
- Module version trong `module-info.java` hoặc module metadata.
- Version hiển thị trong cửa sổ About hoặc log của ứng dụng.
- Version package do `jpackage --app-version` đặt.

Nếu mỗi nơi được nhập thủ công, các giá trị có thể lệch nhau.

Nên chọn một nguồn version duy nhất trong build pipeline, sau đó truyền cùng giá trị vào các bước cần thiết. Ví dụ, pipeline lấy `2.4.1` từ biến `APP_VERSION` để:

1. Gán version cho artifact Maven/Gradle.
2. Ghi version vào manifest/resource nếu ứng dụng cần hiển thị.
3. Đặt `--app-version` khi chạy `jpackage`.
4. Đặt package revision hoặc upgrade identifier theo nền tảng.
5. Ghi version và checksum vào release manifest.

Ví dụ lệnh shell dùng biến môi trường:

~~~bash
APP_VERSION=2.4.1

jpackage --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version "$APP_VERSION" \
  --dest dist
~~~

Trong PowerShell:

~~~powershell
$env:APP_VERSION = "2.4.1"

jpackage --type app-image `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version $env:APP_VERSION `
  --dest dist
~~~

Cần bảo đảm biến version được tạo từ tag/release metadata đáng tin cậy và được ghi lại trong log của build.

## 9. Thực hành: đóng gói một ứng dụng có version

Tạo tệp `src/VersionDemo.java`:

~~~java
public final class VersionDemo {
    public static void main(String[] args) {
        System.out.println("VersionDemo 2.4.1");
    }
}
~~~

Tạo thư mục đầu vào và biên dịch:

~~~bash
mkdir -p build/classes input
javac -d build/classes src/VersionDemo.java
jar --create --file input/VersionDemo.jar \
  --main-class VersionDemo \
  -C build/classes .
~~~

Trên Windows PowerShell, tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force build/classes,input | Out-Null
~~~

Kiểm tra JAR:

~~~bash
jar --list --file input/VersionDemo.jar
~~~

Đầu ra có thể gồm:

~~~text
META-INF/
META-INF/MANIFEST.MF
VersionDemo.class
~~~

Tạo application image:

~~~bash
jpackage --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --vendor "Example Studio" \
  --dest dist
~~~

Application image chứa launcher, JAR và runtime image được tạo bởi `jpackage`/`jlink`. Chạy launcher trong thư mục image để xác nhận ứng dụng hoạt động. Chương trình in:

~~~text
VersionDemo 2.4.1
~~~

Khi cần tạo bộ cài native, chạy lệnh theo nền tảng đích.

**Windows MSI:**

~~~powershell
jpackage --type msi `
  --input input `
  --main-jar VersionDemo.jar `
  --name VersionDemo `
  --app-version 2.4.1 `
  --win-upgrade-uuid "12345678-1234-5678-9abc-def012345678" `
  --dest dist
~~~

**Linux DEB:**

~~~bash
jpackage --type deb \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --linux-app-release 1 \
  --linux-package-name versiondemo \
  --dest dist
~~~

**macOS PKG:**

~~~bash
jpackage --type pkg \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --mac-package-identifier com.example.versiondemo \
  --dest dist
~~~

Các lệnh native phải được chạy trên hệ điều hành đích với công cụ đóng gói cần thiết. Ví dụ, tài liệu JDK 21 nêu WiX 3.0 trở lên là yêu cầu cho Windows packaging; Linux cần công cụ tạo DEB/RPM tương ứng; macOS cần công cụ của nền tảng khi ký hoặc tùy chỉnh package.

## 10. Kiểm tra version sau khi đóng gói

Không nên chỉ nhìn tên file để kết luận version đã đúng. Hãy kiểm tra metadata trong artifact và thử cài đặt.

### 10.1. Kiểm tra version được yêu cầu trong lệnh build

Ghi lại đầy đủ:

- JDK và `jpackage` version.
- `--app-version`.
- `--type`.
- `--name`.
- Các option version/revision/upgrade theo nền tảng.
- Tên file hoặc thư mục đầu ra.

Có thể dùng `--verbose` để xem thêm thông tin khi packaging:

~~~bash
jpackage --verbose --type app-image \
  --input input \
  --main-jar VersionDemo.jar \
  --name VersionDemo \
  --app-version 2.4.1 \
  --dest dist
~~~

### 10.2. Kiểm tra Linux package metadata

Với DEB:

~~~bash
dpkg-deb --field dist/versiondemo*.deb Package Version
~~~

Với RPM:

~~~bash
rpm -qp --queryformat '%{NAME} %{VERSION}-%{RELEASE}\n' dist/*.rpm
~~~

Đối chiếu `VERSION` với application version và `RELEASE` với Linux package release mà bạn đã chỉ định.

### 10.3. Kiểm tra Windows và macOS

Với MSI/EXE, kiểm tra metadata của installer bằng công cụ đọc Windows Installer hoặc thuộc tính file, sau đó thử cài đặt bản mới trên máy có bản cũ để xác nhận luồng upgrade.

Với macOS, kiểm tra metadata của application bundle trong `Info.plist`, identifier và thông tin version; sau đó thử cài đặt package trên hệ thống có bản trước để xác nhận ứng dụng được nhận diện đúng.

Các công cụ và trường metadata cụ thể phụ thuộc định dạng package. Điều quan trọng là xác nhận cả version hiển thị lẫn danh tính sản phẩm dùng cho nâng cấp.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Package luôn có version `1.0` | Không truyền `--app-version` | Truyền version release rõ ràng |
| Dùng `jpackage --version` nhưng tên package không đổi | Đã kiểm tra version của tool, không đặt version ứng dụng | Dùng `--app-version` |
| Tên artifact sai version | `--app-version` không lấy từ cùng nguồn với version build | Đồng bộ biến version từ build pipeline |
| DEB/RPM có version đúng nhưng revision sai | Chưa đặt `--linux-app-release` hoặc dùng sai giá trị | Tách application version và package release |
| Windows không nhận diện bản mới như cùng sản phẩm | UUID nâng cấp bị đổi hoặc cấu hình upgrade không phù hợp | Kiểm tra `--win-upgrade-uuid` và cấu hình Windows Installer |
| macOS nhận diện ứng dụng như một app khác | Application identifier bị thay đổi | Giữ ổn định `--mac-package-identifier` |
| Package build được nhưng không cài đặt/nâng cấp như mong đợi | Chỉ kiểm tra tên file, chưa thử installer thực tế | Test cài mới, nâng cấp và gỡ cài đặt |
| Version có hậu tố không được package backend chấp nhận | Định dạng version không phù hợp nền tảng | Dùng định dạng version được package manager hỗ trợ |
| Máy khác hiển thị version không như ứng dụng | Package metadata và version trong code khác nhau | Đồng bộ version trong source/build/package |
| Không tạo được native package | Thiếu công cụ đóng gói của hệ điều hành đích | Cài prerequisite và chạy trên nền tảng phù hợp |

## 12. Quy trình phát hành khuyến nghị

Với mỗi lần phát hành, có thể áp dụng trình tự:

1. **Chọn application version:** xác định version sản phẩm, ví dụ `2.4.2`.
2. **Chốt nguồn version:** lấy từ tag Git hoặc biến build để tránh nhập thủ công ở nhiều nơi.
3. **Build JAR/module:** biên dịch, chạy test và tạo artifact.
4. **Tạo application image:** chạy `jpackage --type app-image` để kiểm tra launcher, runtime và tài nguyên.
5. **Chọn package type:** `msi`/`exe`, `deb`/`rpm` hoặc `pkg`/`dmg` theo nền tảng.
6. **Đặt metadata version:** dùng `--app-version`.
7. **Đặt platform identity/revision:** giữ Windows upgrade UUID và macOS identifier ổn định; tăng Linux package release khi cần revision đóng gói.
8. **Tạo package native:** chạy trên hệ điều hành đích.
9. **Kiểm tra metadata:** đọc version, revision, tên package và identifier từ artifact.
10. **Kiểm thử nâng cấp:** thử cài mới, nâng từ bản trước và gỡ cài đặt.
11. **Lưu release manifest:** ghi version, JDK version, package type, nền tảng, checksum và nguồn commit.

## 13. Ghi nhớ

- `--app-version` là version của ứng dụng/package; mặc định JDK 21 là `1.0`.
- `--version` in version của công cụ `jpackage`.
- Tên package được tạo dựa trên tên ứng dụng và version.
- Linux có `--linux-app-release` riêng cho RPM Release hoặc Debian revision.
- Windows có `--win-upgrade-uuid` để nhận diện nhóm package liên quan trong quá trình nâng cấp.
- macOS có `--mac-package-identifier` để định danh ứng dụng ổn định.
- Version package không tự đồng bộ mọi version trong Maven, Gradle, manifest hoặc giao diện ứng dụng.
- Hãy build và kiểm thử package trên đúng hệ điều hành đích.

Tài liệu tham khảo:

- [The jpackage Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [Packaging Tool User's Guide — Java SE 21, Basic Packaging and Package Metadata](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-tool-user-guide.pdf)
- [Packaging Overview — Java SE 21](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html)
- [Microsoft: Preparing an Application for Future Major Upgrades](https://learn.microsoft.com/en-us/windows/win32/msi/preparing-an-application-for-future-major-upgrades)