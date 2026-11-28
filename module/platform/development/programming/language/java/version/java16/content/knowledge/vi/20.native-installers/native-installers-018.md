# Đối chiếu checksum, phiên bản runtime và hành vi gói trước phát hành

## 1. Vì sao phải kiểm tra gói trước khi phát hành?

Một ứng dụng Java có thể chạy tốt trong môi trường phát triển nhưng gặp lỗi sau khi đóng gói hoặc cài trên máy người dùng. Nguyên nhân có thể đến từ file package bị thay đổi, runtime đi kèm không đúng phiên bản, thiếu module, sai metadata hoặc hành vi cài đặt khác với dự kiến.

Với `jpackage`, quy trình phát hành cần kiểm tra ít nhất ba nhóm:

1. **Tính toàn vẹn của artifact:** checksum của file phát hành có khớp với checksum được tạo sau khi hoàn tất đóng gói và ký hay không.
2. **Runtime thực tế:** application image chứa runtime nào, runtime đó có đúng phiên bản và module ứng dụng cần hay không.
3. **Hành vi của package:** installer có cài đúng ứng dụng, launcher, runtime, shortcut, file association và gỡ cài đặt đúng hay không.

Cần phân biệt ba phiên bản thường xuất hiện trong quy trình:

- Phiên bản ứng dụng, được khai báo qua metadata như `--app-version`.
- Phiên bản JDK dùng để biên dịch hoặc chạy công cụ đóng gói.
- Phiên bản Java runtime thực sự được đặt trong application image.

Ba giá trị này có liên quan nhưng không nhất thiết giống nhau. Người phát hành phải kiểm tra runtime nằm trong gói thay vì suy luận từ JDK cài trên máy build.

Mục tiêu bài học:

- Tạo và đối chiếu checksum SHA-256 cho artifact.
- Phân biệt checksum với chữ ký số.
- Xác minh chữ ký theo nền tảng.
- Tìm và kiểm tra runtime được đóng gói cùng ứng dụng.
- Xác nhận phiên bản ứng dụng và metadata của package.
- Kiểm thử cài đặt, chạy, nâng cấp và gỡ cài đặt trên môi trường sạch.
- Lập checklist và lưu bằng chứng trước khi phát hành.

## 2. Phân biệt application image, installer và artifact phát hành

`jpackage` có thể tạo application image hoặc native installer. Hai loại đầu ra phục vụ các mục đích kiểm tra khác nhau.

| Đầu ra | Mục đích | Cách kiểm tra |
| --- | --- | --- |
| Application image | Thư mục ứng dụng gồm launcher, file ứng dụng và runtime. | Chạy trực tiếp launcher, kiểm tra runtime và cấu hình. |
| Native installer | Gói cài đặt như MSI, EXE, DEB, RPM, PKG hoặc DMG. | Kiểm tra metadata, chữ ký, cài đặt, nâng cấp và gỡ cài đặt. |
| Archive phát hành | File ZIP/TAR chứa application image hoặc tài liệu phân phối. | Kiểm tra nội dung archive và checksum của archive cuối. |

Nên tạo application image trước:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 2.1.0 \
    --dest dist
~~~

Sau đó chạy thử launcher trong application image. Khi image đạt yêu cầu, tạo installer từ image đó:

~~~bash
jpackage \
    --type msi \
    --name AcmeDesk \
    --app-version 2.1.0 \
    --app-image dist/AcmeDesk \
    --dest release
~~~

`msi` là định dạng Windows. Trên Linux và macOS, chọn loại package phù hợp với nền tảng. `jpackage` không tạo native package chéo nền tảng; mỗi nền tảng đích cần quy trình đóng gói và kiểm thử tương ứng.

Không nên chỉ kiểm tra lệnh `jpackage` kết thúc thành công rồi xem package là sẵn sàng phát hành. Lệnh thành công xác nhận công cụ đã tạo đầu ra, không chứng minh ứng dụng hoạt động đúng trên máy người dùng.

## 3. Checksum là gì và xác nhận điều gì?

Checksum là giá trị băm được tính từ nội dung file. Với cùng một thuật toán và cùng một nội dung, giá trị băm sẽ giống nhau. Chỉ cần một thay đổi nhỏ trong file cũng làm giá trị băm thay đổi với xác suất rất cao.

Trong quy trình phát hành, checksum giúp:

- Phát hiện file bị hỏng khi tải xuống hoặc sao chép.
- So sánh artifact ở hai vị trí.
- Xác nhận file người dùng nhận được giống file đã được ghi nhận trong manifest phát hành.
- Phát hiện việc artifact bị thay đổi sau khi tạo manifest.

Dùng SHA-256 cho checksum phát hành:

~~~text
SHA256 (AcmeDesk-2.1.0.msi) = <64 ký tự hex>
~~~

Không dùng MD5 hoặc SHA-1 làm cơ chế bảo vệ tính toàn vẹn trước hành vi giả mạo. Các thuật toán này không còn phù hợp cho mục đích bảo mật hiện đại.

### Checksum không tự xác thực người phát hành

Nếu package và file checksum được tải từ cùng một nguồn đã bị xâm nhập, kẻ tấn công có thể thay cả hai. Vì vậy:

- Checksum giúp so sánh nội dung.
- Chữ ký số giúp xác minh nguồn ký và tính toàn vẹn theo chuỗi tin cậy.
- Manifest checksum nên được phân phối qua kênh tin cậy hoặc được ký số.

Checksum và chữ ký số bổ sung cho nhau, không thay thế nhau.

## 4. Tạo SHA-256 trên Windows

PowerShell có cmdlet `Get-FileHash`. Thuật toán mặc định hiện nay là SHA-256, nhưng nên ghi rõ thuật toán trong lệnh phát hành:

~~~powershell
Get-FileHash .\AcmeDesk-2.1.0.msi -Algorithm SHA256
~~~

Kết quả có các trường:

- `Algorithm`: thuật toán được dùng.
- `Hash`: giá trị băm.
- `Path`: đường dẫn file.

Có thể ghi kết quả vào manifest:

~~~powershell
$artifact = ".\AcmeDesk-2.1.0.msi"
$hash = (Get-FileHash $artifact -Algorithm SHA256).Hash
"$hash  AcmeDesk-2.1.0.msi" |
    Set-Content -Encoding ascii .\SHA256SUMS.txt
~~~

Để kiểm tra file tải xuống:

~~~powershell
$expected = "<SHA256_EXPECTED>"
$actual = (Get-FileHash .\AcmeDesk-2.1.0.msi -Algorithm SHA256).Hash

if ($actual -ne $expected) {
    throw "Checksum mismatch"
}

"Checksum verified"
~~~

Không chép giá trị hash từ ví dụ vào release thực tế. `<SHA256_EXPECTED>` phải được thay bằng giá trị lấy từ manifest phát hành đáng tin cậy.

## 5. Tạo và kiểm tra SHA-256 trên Linux và macOS

Trên Linux có thể dùng `sha256sum`:

~~~bash
sha256sum AcmeDesk-2.1.0.deb
~~~

Tạo manifest:

~~~bash
sha256sum AcmeDesk-2.1.0.deb > SHA256SUMS
~~~

Kiểm tra file theo manifest:

~~~bash
sha256sum --check SHA256SUMS
~~~

Trên macOS, có thể dùng `shasum`:

~~~bash
shasum -a 256 AcmeDesk-2.1.0.dmg
~~~

Nếu cần kiểm tra archive chứa application image, hãy tính hash trên archive cuối cùng:

~~~bash
tar -czf AcmeDesk-2.1.0-linux.tar.gz AcmeDesk/
sha256sum AcmeDesk-2.1.0-linux.tar.gz
~~~

Một thư mục application image không có một checksum file đơn giản như installer. Có hai cách phổ biến:

- Đóng gói thư mục thành ZIP/TAR rồi tính checksum cho archive cuối.
- Tạo manifest gồm checksum của từng file và lưu cấu trúc đường dẫn tương ứng.

Nếu tạo archive, hãy tính checksum sau khi archive đã hoàn tất. Mọi thay đổi sau đó, kể cả đổi file hoặc nén lại, đều tạo artifact khác và cần checksum mới.

## 6. Thời điểm tính checksum trong quy trình phát hành

Checksum phải đại diện cho đúng file người dùng tải về. Vì vậy, hãy tính checksum sau khi mọi thao tác làm thay đổi artifact đã hoàn tất.

Một thứ tự tham khảo:

1. Build ứng dụng và chuẩn bị runtime.
2. Tạo application image.
3. Kiểm thử application image.
4. Tạo native installer.
5. Ký package hoặc bundle nếu nền tảng yêu cầu.
6. Xác minh chữ ký.
7. Tính SHA-256 trên file cuối cùng sau khi ký.
8. Tạo manifest checksum.
9. Ký manifest hoặc phát hành qua kênh tin cậy.
10. Tải lại artifact từ nơi phân phối và đối chiếu checksum.

Không tính checksum trước khi ký rồi dùng giá trị đó cho file sau khi ký. Chữ ký nhúng hoặc metadata ký có thể làm thay đổi byte của file, khiến checksum trước và sau ký khác nhau.

Nếu package được ký lại hoặc được sửa metadata sau khi tính hash, phải tạo lại checksum và manifest.

## 7. Phân biệt checksum và chữ ký số

| Đặc điểm | Checksum SHA-256 | Chữ ký số |
| --- | --- | --- |
| Dựa trên | Nội dung file và thuật toán hash. | Nội dung file, khóa riêng và chứng thư/khóa công khai. |
| Phát hiện thay đổi file | Có, khi so với giá trị tin cậy. | Có, khi xác minh chữ ký thành công. |
| Xác nhận danh tính người ký | Không. | Có thể xác nhận danh tính theo chuỗi tin cậy và chính sách xác minh. |
| Cần khóa/chứng thư | Không cần để tính hash. | Có. |
| Phân phối | Có thể dùng manifest checksum. | Chữ ký nhúng hoặc chữ ký tách rời tùy định dạng. |

Một file checksum đặt cạnh package không chứng minh package do nhà phát hành chính thức tạo. Để xác thực nguồn, người dùng cần xác minh chữ ký số hoặc lấy manifest đã ký từ một kênh tin cậy.

Trước phát hành, cần kiểm tra:

- Chữ ký có hợp lệ không.
- Chứng thư có đúng publisher dự kiến không.
- Chuỗi chứng thư có được hệ điều hành tin cậy không.
- Chữ ký có timestamp phù hợp khi chính sách yêu cầu không.
- File có bị thay đổi sau khi ký không.

## 8. Xác minh chữ ký trên Windows

Nếu package hoặc executable được ký Authenticode, có thể dùng SignTool từ Windows SDK:

~~~powershell
signtool verify /pa /v .\AcmeDesk-2.1.0.msi
~~~

Các phần quan trọng:

- `verify` yêu cầu kiểm tra chữ ký.
- `/pa` dùng Default Authentication Verification Policy.
- `/v` hiển thị thông tin chi tiết hơn, gồm signer và trạng thái kiểm tra.

Có thể kiểm tra thêm bằng PowerShell:

~~~powershell
Get-AuthenticodeSignature .\AcmeDesk-2.1.0.msi |
    Format-List Status, StatusMessage, SignerCertificate
~~~

Khi review kết quả, không chỉ nhìn thấy trạng thái có chữ ký. Hãy kiểm tra:

- `Status` là hợp lệ.
- Publisher trong chứng thư đúng tổ chức phát hành.
- Chứng thư còn hiệu lực hoặc có timestamp hợp lệ theo chính sách.
- Chữ ký bao phủ đúng file package được phát hành.

## 9. Xác minh chữ ký trên macOS

Với ứng dụng dạng `.app`, dùng `codesign` để xác minh code signature:

~~~bash
codesign --verify --deep --strict --verbose=2 "AcmeDesk.app"
~~~

Lệnh này kiểm tra tính hợp lệ của chữ ký và các thành phần được seal theo cấu trúc code signing.

Có thể xem thông tin signer:

~~~bash
codesign --display --verbose=4 "AcmeDesk.app"
~~~

Để đánh giá Gatekeeper có chấp nhận ứng dụng theo policy trên máy kiểm tra hay không:

~~~bash
spctl --assess --type execute --verbose=4 "AcmeDesk.app"
~~~

Các bước này trả lời những câu hỏi khác nhau:

- `codesign --verify` kiểm tra tính hợp lệ của code signature.
- `spctl --assess` đánh giá ứng dụng theo policy bảo mật của macOS trên máy đó.

Chữ ký hợp lệ không tự chứng minh ứng dụng đã được notarize hoặc chắc chắn được chấp nhận trong mọi môi trường. Nếu phát hành ngoài App Store theo quy trình yêu cầu notarization, hãy kiểm tra trạng thái notarization và thử cài/chạy trên phiên bản macOS mục tiêu.

Sau khi ký hoặc notarize, tính lại checksum của file DMG hoặc archive cuối cùng được phân phối.

## 10. Kiểm tra package trên Linux

Với gói DEB, xem metadata và nội dung:

~~~bash
dpkg-deb --info AcmeDesk-2.1.0.deb
dpkg-deb --contents AcmeDesk-2.1.0.deb
~~~

Với gói RPM:

~~~bash
rpm -qpi AcmeDesk-2.1.0.rpm
rpm -qpl AcmeDesk-2.1.0.rpm
rpm --checksig --verbose AcmeDesk-2.1.0.rpm
~~~

Các lệnh này giúp kiểm tra:

- Tên và phiên bản package.
- Kiến trúc package.
- Metadata về maintainer/vendor.
- Danh sách file sẽ được cài.
- Digest và chữ ký RPM theo cấu hình xác minh của hệ thống.

Với DEB, tính toàn vẹn và xác thực nguồn trong hệ thống phân phối thường được bảo vệ qua metadata và chữ ký của repository APT. `dpkg-deb --info` và `--contents` chủ yếu kiểm tra metadata/cấu trúc package, không phải xác minh publisher signature cho file DEB độc lập.

Sau khi xem nội dung package, cần cài thử trên máy hoặc container Linux sạch có đúng hệ phân phối và kiến trúc được hỗ trợ. Xác minh launcher, thư mục cài, quyền file và hành vi gỡ cài đặt.

## 11. Kiểm tra runtime thực sự được đóng gói

`jpackage` có thể tự tạo runtime bằng `jlink` hoặc nhận runtime đã chuẩn bị qua `--runtime-image`.

Nếu không truyền `--runtime-image`, công cụ tạo runtime dựa trên JDK dùng để chạy `jpackage` và các module cần thiết cho ứng dụng. Nếu truyền runtime có sẵn, application image sử dụng runtime được chỉ định.

Vì vậy, lệnh `java --version` chạy trong terminal của máy build không chứng minh runtime trong package có cùng phiên bản.

### Vị trí runtime trong application image

Cấu trúc thư mục phụ thuộc nền tảng. Ví dụ thường gặp:

~~~text
Linux:
AcmeDesk/
  bin/
    AcmeDesk
  lib/
    app/
    runtime/
      bin/java

Windows:
AcmeDesk/
  AcmeDesk.exe
  app/
  runtime/
    bin/java.exe

macOS:
AcmeDesk.app/
  Contents/
    MacOS/
    app/
    runtime/
      Contents/
        Home/
          bin/java
~~~

Đây là bố cục tham khảo của application image. Một số chi tiết triển khai có thể thay đổi theo JDK và nền tảng. Dùng đường dẫn runtime thực tế trong image đang kiểm tra.

### Xem phiên bản runtime đi kèm

Trên Linux:

~~~bash
./AcmeDesk/lib/runtime/bin/java --version
~~~

Trên Windows:

~~~powershell
.\AcmeDesk\runtime\bin\java.exe --version
~~~

Trên macOS:

~~~bash
./AcmeDesk.app/Contents/runtime/Contents/Home/bin/java --version
~~~

So sánh kết quả với phiên bản Java mục tiêu của sản phẩm. Nếu sử dụng custom runtime image, xác minh chính runtime nguồn trước khi đóng gói và xác minh lại runtime đã copy vào application image.

## 12. Kiểm tra module và runtime metadata

Runtime được tạo bằng `jlink` có thể chỉ chứa những module cần thiết. Không giả định nó giống một JDK đầy đủ được cài trên máy phát triển.

Có thể liệt kê module trong runtime:

~~~bash
./runtime/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
.\runtime\bin\java.exe --list-modules
~~~

Kiểm tra module ứng dụng cần, chẳng hạn:

- `java.base`
- `java.desktop` nếu ứng dụng dùng AWT/Swing.
- `java.logging` nếu dùng logging API.
- `java.sql` nếu ứng dụng dùng JDBC API.
- Các module khác theo dependency thực tế.

Không thêm module chỉ vì nó thường có trong JDK đầy đủ. Hãy xác nhận ứng dụng và thư viện thực sự cần module nào, sau đó chạy smoke test trên runtime tối giản.

Runtime image thường có file `release` chứa thông tin build và cấu hình runtime. Có thể đọc file này để đối chiếu metadata:

~~~bash
cat runtime/release
~~~

Trên PowerShell:

~~~powershell
Get-Content .\runtime\release
~~~

File `release` là bằng chứng bổ sung; lệnh chạy `java --version` và kiểm thử ứng dụng trên chính runtime được đóng gói vẫn là bước cần thiết.

## 13. Phân biệt phiên bản ứng dụng, JDK đóng gói và runtime

Một bản phát hành có thể ghi nhận ba giá trị khác nhau:

| Giá trị | Nguồn kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Application version | Metadata package và cấu hình `--app-version` | Phiên bản sản phẩm được phát hành. |
| Packaging JDK | `java --version` và `jpackage --version` trên máy build | Bộ công cụ dùng để tạo application image/installer. |
| Bundled runtime | Chạy `runtime/bin/java --version` trong image | Phiên bản Java mà launcher đóng gói sẽ sử dụng. |

Ví dụ hồ sơ build:

~~~text
Application: AcmeDesk 2.1.0
Packaging JDK: 21.0.x
jpackage: 21.0.x
Bundled runtime: 21.0.x
Target OS: Windows 11 x64
Package: AcmeDesk-2.1.0.msi
~~~

Các số phiên bản trong ví dụ chỉ minh họa cách ghi hồ sơ. Thay bằng giá trị thực từ build của bạn.

Nếu packaging JDK và bundled runtime khác phiên bản, hãy ghi rõ lý do và xác minh tương thích. Tránh dùng một dòng “Java version” chung chung vì không cho biết nó nói đến công cụ build hay runtime người dùng chạy.

## 14. Kiểm thử hành vi cài đặt và chạy

Sau khi checksum, signature và runtime đạt yêu cầu, cài package trên môi trường sạch.

Môi trường sạch nên:

- Không có JDK/JRE phát triển cài sẵn nếu sản phẩm hứa tự mang runtime.
- Không phụ thuộc biến môi trường `JAVA_HOME` hoặc `PATH` của máy build.
- Có user account và quyền cài đặt tương tự người dùng mục tiêu.
- Dùng đúng hệ điều hành, kiến trúc CPU và phiên bản nền tảng được hỗ trợ.
- Không có thư mục hoặc file cũ từ lần cài trước làm che giấu lỗi.

Các hành vi cần kiểm tra:

1. Installer khởi chạy và hoàn tất không lỗi.
2. Tên, phiên bản, vendor và vị trí cài đúng metadata.
3. Launcher chính xuất hiện đúng vị trí.
4. Shortcut/menu entry được tạo theo cấu hình.
5. Ứng dụng chạy bằng runtime đi kèm.
6. Các chức năng chính hoạt động.
7. Tệp cấu hình, log và dữ liệu được ghi vào vị trí phù hợp.
8. File association mở đúng launcher nếu package có khai báo.
9. Quyền truy cập file và thư mục đúng với user mục tiêu.
10. Ứng dụng không yêu cầu JDK ngoài nếu không nằm trong yêu cầu sản phẩm.

Nếu ứng dụng khởi động được trên máy build nhưng không chạy trên máy sạch, kiểm tra log launcher, runtime đi kèm, native dependency và quyền truy cập trước khi thay đổi package.

## 15. Kiểm tra nâng cấp, gỡ cài đặt và dữ liệu người dùng

Package cần được kiểm tra qua toàn bộ vòng đời, không chỉ cài lần đầu.

### Nâng cấp

Thử nâng cấp từ phiên bản đang phát hành trước đó:

- Package mới có nhận diện đúng sản phẩm cũ không?
- File ứng dụng được cập nhật đầy đủ không?
- Runtime cũ có được thay bằng runtime mới không?
- Shortcut và file association có còn đúng không?
- Cấu hình và dữ liệu người dùng có được bảo toàn theo chính sách không?

### Gỡ cài đặt

Sau khi uninstall, xác minh:

- File ứng dụng và runtime được gỡ đúng.
- Shortcut/menu entry được dọn.
- File association được khôi phục hoặc gỡ theo thiết kế.
- Dữ liệu người dùng được giữ hay xóa đúng chính sách đã công bố.
- Không còn service hoặc process do package tạo ra mà không được dọn.

Không xóa dữ liệu người dùng một cách bất ngờ khi uninstall. Nếu sản phẩm giữ lại cấu hình hoặc dữ liệu, ghi rõ vị trí và chính sách đó trong tài liệu vận hành.

### Cài mới sau khi gỡ

Thử cài lại sau uninstall để phát hiện file hoặc registry entry cũ gây xung đột. Kiểm tra cả cài đặt theo user và cài đặt toàn hệ thống nếu sản phẩm hỗ trợ hai chế độ.

## 16. Quy trình kiểm tra trước khi phát hành

Có thể dùng quy trình sau cho mỗi release:

1. Ghi lại commit/source revision và phiên bản ứng dụng.
2. Ghi lại vendor, version của JDK và `jpackage` dùng để build.
3. Tạo application image bằng `--type app-image`.
4. Kiểm tra runtime version bằng executable trong application image.
5. Kiểm tra module cần thiết và chạy smoke test.
6. Tạo native installer trên đúng nền tảng.
7. Kiểm tra metadata và danh sách file của package.
8. Ký package/bundle theo yêu cầu nền tảng.
9. Xác minh chữ ký và publisher.
10. Tính SHA-256 trên artifact cuối cùng sau khi ký.
11. Tạo manifest checksum và bảo vệ manifest bằng kênh tin cậy hoặc chữ ký.
12. Cài package trên máy sạch.
13. Kiểm tra launch, chức năng, shortcut, quyền và file association.
14. Kiểm tra upgrade và uninstall.
15. Tải artifact từ nơi phát hành và xác minh lại checksum.
16. Lưu kết quả kiểm thử, log, checksum, chữ ký và thông tin runtime cùng release.

Nếu một bước thất bại, dừng phát hành artifact đó cho đến khi nguyên nhân được xác định và kiểm thử lại.

## 17. Checklist phát hành

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Application version | Khớp version đã phê duyệt. |
| Packaging JDK | Ghi nhận vendor và version thực tế. |
| jpackage | Ghi nhận version công cụ. |
| Bundled runtime | Chạy `java --version` từ runtime trong image và đối chiếu mục tiêu. |
| Required modules | Runtime có đủ module cho chức năng đã kiểm thử. |
| Package metadata | Tên, version, vendor, kiến trúc và loại package đúng. |
| Package signature | Chữ ký hợp lệ, đúng publisher khi nền tảng yêu cầu. |
| SHA-256 | Checksum được tính từ artifact cuối sau ký. |
| Checksum manifest | Được lưu hoặc phân phối qua kênh tin cậy. |
| Clean install | Cài đặt được trên môi trường không có JDK phát triển. |
| Launch | Launcher dùng runtime đi kèm và mở được ứng dụng. |
| Core functions | Smoke test đạt. |
| Upgrade | Nâng cấp từ phiên bản trước đạt. |
| Uninstall | Gỡ đúng và xử lý dữ liệu theo chính sách. |
| Download verification | File tải từ kênh phát hành có checksum khớp. |
| Release evidence | Log, kết quả kiểm tra và thông tin build được lưu. |

## 18. Lỗi thường gặp và cách khắc phục

1. **Tính checksum trước khi ký:** chữ ký có thể thay đổi file; tính lại hash sau khi ký.
2. **So sánh checksum với nguồn không tin cậy:** lấy manifest từ kênh phát hành tin cậy hoặc xác minh chữ ký manifest.
3. **Dùng MD5 hoặc SHA-1 cho bảo vệ release:** dùng SHA-256 hoặc thuật toán mạnh được chính sách phát hành chấp nhận.
4. **Chỉ kiểm tra java --version trên máy build:** chạy executable Java nằm trong runtime của application image.
5. **Nhầm application version với Java version:** ghi riêng version sản phẩm, packaging JDK và bundled runtime.
6. **Giả định runtime là JDK đầy đủ:** runtime từ `jlink` thường chỉ chứa module và file cần thiết; kiểm tra module và chức năng thực tế.
7. **Chỉ chạy application image trên máy phát triển:** cài installer trên môi trường sạch để phát hiện dependency ngoài.
8. **Chỉ kiểm tra installer tạo thành công:** kiểm tra metadata, signature, cài đặt, launcher, upgrade và uninstall.
9. **Không kiểm tra package sau khi tải xuống:** tính lại checksum trên file tải về.
10. **Cho rằng chữ ký hợp lệ đồng nghĩa ứng dụng đã được hệ điều hành chấp nhận:** kiểm tra thêm policy nền tảng, notarization hoặc trust chain khi áp dụng.
11. **Dùng cấu trúc runtime hard-code cho mọi nền tảng:** xác định vị trí runtime theo application image của nền tảng và JDK đang dùng.
12. **Bỏ qua file association và shortcut:** kiểm tra hành vi người dùng thực tế sau khi cài.
13. **Không lưu hồ sơ build:** ghi lại source revision, JDK, jpackage, runtime, package hash và kết quả kiểm thử.
14. **Thay đổi artifact sau khi kiểm tra:** mọi sửa đổi sau ký hoặc sau khi tính hash đều cần xác minh lại.

## 19. Bài tập thực hành

1. Tạo application image bằng `jpackage --type app-image` và xác định vị trí runtime trên hệ điều hành đang dùng.
2. Chạy `java --version` từ runtime nằm trong application image; so sánh với JDK dùng để chạy `jpackage`.
3. Dùng `java --list-modules` để liệt kê module của runtime và đối chiếu với module ứng dụng cần.
4. Tạo SHA-256 cho một installer bằng PowerShell `Get-FileHash`.
5. Tạo manifest bằng `sha256sum` và xác minh với `sha256sum --check` trên Linux.
6. Thay đổi một byte trong bản sao package và quan sát checksum khác nhau.
7. Giải thích vì sao checksum và chữ ký số giải quyết hai vấn đề khác nhau.
8. Xác minh chữ ký MSI/EXE bằng `signtool verify /pa /v`.
9. Xác minh bundle macOS bằng `codesign --verify --deep --strict` và đánh giá Gatekeeper bằng `spctl`.
10. Kiểm tra metadata và danh sách file của DEB/RPM.
11. Cài package trên VM không có JDK phát triển và xác nhận ứng dụng chạy bằng runtime đóng gói.
12. Thử nâng cấp từ phiên bản cũ, sau đó uninstall và cài mới.
13. Lập release manifest gồm application version, packaging JDK, bundled runtime, target platform, package type và SHA-256.
14. Viết checklist kiểm thử cho một ứng dụng desktop có shortcut, file association và dữ liệu người dùng.

## Ghi nhớ

Trước khi phát hành, hãy kiểm tra artifact cuối bằng SHA-256 và xác minh chữ ký số theo nền tảng. Checksum xác nhận nội dung file khớp với giá trị tham chiếu; chữ ký số giúp xác minh nguồn ký và tính toàn vẹn theo chuỗi tin cậy. Tính checksum sau khi ký và bảo vệ manifest bằng kênh phân phối đáng tin cậy. Với `jpackage`, kiểm tra runtime thực sự nằm trong application image bằng cách chạy executable Java bên trong runtime, không suy luận từ JDK của máy build. Đối chiếu riêng phiên bản ứng dụng, JDK đóng gói và bundled runtime. Cuối cùng, cài thử trên môi trường sạch, kiểm tra launcher và chức năng, nâng cấp, gỡ cài đặt, rồi tải lại artifact từ kênh phát hành để xác minh checksum lần cuối.

**Tài liệu tham khảo chính thức:**

- [JDK 16 – The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Current jpackage – Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Current jpackage – Command Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Microsoft Learn – Get-FileHash](https://learn.microsoft.com/en-us/powershell/module/Microsoft.PowerShell.Utility/Get-FileHash)
- [Microsoft Learn – Use SignTool to Verify a File Signature](https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-verify-a-file-signature)
- [Apple Developer – Verify a code signature](https://developer.apple.com/documentation/technotes/tn3161-inside-code-signing-certificates)
- [RPM – rpmkeys and package signature verification](https://rpm.org/docs/latest/man/rpmkeys.8.html)
