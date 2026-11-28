# Quy trình ký gói trên nền tảng đích và kiểm tra chữ ký đầu ra

Khi phát hành ứng dụng Java dưới dạng native installer, tạo được file EXE, MSI, PKG, DMG, DEB hoặc RPM mới chỉ hoàn thành bước đóng gói. Trước khi phân phối, cần ký artifact bằng danh tính phù hợp với hệ điều hành, xác minh chữ ký và kiểm tra lại đúng file cuối cùng sẽ được tải xuống hoặc cài đặt.

Quy trình ký khác nhau theo nền tảng:

- Windows dùng Authenticode để ký các file thực thi và installer như EXE, MSI.
- macOS dùng code signing cho app bundle, executable và installer; ứng dụng Developer ID phân phối trực tiếp còn cần notarization.
- RPM hỗ trợ chữ ký OpenPGP gắn trực tiếp vào package.
- Với DEB, APT thông thường xác thực repository thông qua chữ ký của metadata Release và checksum package. Đây là chuỗi xác thực repository, không phải chữ ký OpenPGP gắn trực tiếp trên từng file DEB.

Trong module Java 16, jpackage là công cụ đóng gói ổn định và vẫn được dùng trong quy trình Java hiện đại. Bài này tập trung vào việc ký artifact trên runner đúng nền tảng, bảo vệ khóa ký, xác minh danh tính và tính toàn vẹn, kiểm tra timestamp/notarization, rồi chỉ phát hành artifact đã được xác minh. Cần kiểm tra tùy chọn của đúng JDK và công cụ ký của hệ điều hành; không giả định jpackage tự ký mọi loại package.

## 1. Chữ ký package bảo vệ điều gì?

Chữ ký số gắn artifact với một danh tính ký và cho phép bên nhận kiểm tra nội dung có bị thay đổi sau khi ký hay không. Tùy hệ sinh thái, chữ ký còn giúp package manager hoặc hệ điều hành xác thực nguồn phát hành.

Một quy trình ký tốt cần kiểm tra nhiều điều:

1. **Danh tính:** chứng thư hoặc khóa công khai thuộc đúng nhà phát hành.
2. **Tính toàn vẹn:** nội dung artifact chưa bị thay đổi sau khi ký.
3. **Chuỗi tin cậy:** chứng thư dẫn tới CA hoặc khóa gốc mà máy nhận tin cậy.
4. **Thời điểm ký:** timestamp hợp lệ giúp chữ ký vẫn có thể xác minh sau khi chứng thư ký hết hạn, tùy chính sách và trạng thái thu hồi.
5. **Đúng artifact:** file được xác minh phải chính là file được phát hành.
6. **Đúng chính sách nền tảng:** chữ ký đáp ứng yêu cầu Authenticode, Gatekeeper, APT hoặc RPM của môi trường đích.

Chữ ký không chứng minh phần mềm không có lỗ hổng hoặc mã độc. Nó chứng minh nguồn gốc theo danh tính ký và giúp phát hiện việc thay đổi nội dung đã ký. Notarization của Apple cũng là một bước kiểm tra tự động theo chính sách Apple, không phải kiểm thử chất lượng hay App Review.

## 2. Phân biệt ký code, ký installer và ký repository

Một bản phát hành có thể có nhiều lớp artifact:

| Lớp | Ví dụ | Mục tiêu |
|---|---|---|
| Code bên trong ứng dụng | EXE, DLL, Mach-O, framework, helper | Xác thực thành phần thực thi khi hệ điều hành nạp hoặc chạy. |
| Application image | Thư mục app-image hoặc app bundle | Bảo vệ launcher, runtime và code đi kèm. |
| Native installer | EXE/MSI, PKG, RPM | Xác thực file cài đặt được người dùng tải xuống. |
| Container phân phối | DMG, ZIP | Bảo vệ container hoặc hỗ trợ Gatekeeper/notarization trên macOS. |
| Repository metadata | APT InRelease/Release.gpg, RPM repomd.xml | Xác thực metadata và checksum của package trong repository. |

Ký một lớp không tự động ký các lớp khác. Ví dụ, ký EXE bên trong application image không có nghĩa MSI bao ngoài đã được ký; ký MSI không thay thế việc ký code nhúng nếu chính sách triển khai yêu cầu code signing cho các executable đó.

Tương tự, chữ ký repository APT xác thực metadata và checksum của package mà repository công bố. Nó không phải chữ ký nhúng trực tiếp trên file DEB. Cần biết mình đang xác minh code, installer hay repository để chọn đúng công cụ.

## 3. Quy tắc chung: build và ký trên nền tảng đích

jpackage tạo native package theo nền tảng đang chạy. Không có quy trình cross-platform được jpackage hỗ trợ để tạo installer Windows trên Linux hoặc installer macOS trên Windows. Do đó, pipeline nên có runner tương ứng:

| Artifact | Runner phù hợp | Công cụ ký/xác minh |
|---|---|---|
| EXE/MSI | Windows | SignTool / Windows SDK |
| PKG/DMG/app bundle | macOS | codesign, productsign/pkgbuild/productbuild, notarytool, stapler |
| RPM | Linux thuộc họ RPM hoặc môi trường build tương thích | rpmsign, rpm |
| DEB và APT repository | Linux thuộc họ Debian hoặc môi trường build tương thích | apt-ftparchive, GPG, APT |

Runner phải có phiên bản JDK, SDK, package toolchain và certificate/key được quản lý. Không chuyển private key vào source repository hoặc lưu trong application image.

Quy trình hai giai đoạn app-image rồi installer hữu ích khi cần ký các executable bên trong image trước khi đóng gói installer. Với quy trình trực tiếp, jpackage tạo package trước; những bước ký bổ sung được thực hiện trên artifact sau khi tạo, theo khả năng của từng nền tảng.

## 4. Thứ tự xử lý artifact

Một pipeline tổng quát có thể tổ chức như sau:

~~~text
Source + dependencies
        |
        v
Build JAR and runtime
        |
        v
Create application image
        |
        v
Sign inner code when required
        |
        v
Create native installer/package
        |
        v
Sign final installer or repository metadata
        |
        v
Verify signature, identity, timestamp and integrity
        |
        v
Install/test on a clean target system
        |
        v
Generate checksum and publish the verified artifact
~~~

Không chỉnh sửa file sau khi ký. Nếu thay đổi executable, resource nằm trong vùng chữ ký bảo vệ, installer hoặc metadata repository, phải tạo lại chữ ký tương ứng và xác minh lại.

## 5. Bảo vệ khóa ký và danh tính phát hành

Khóa riêng là tài sản bảo mật quan trọng nhất trong quy trình ký. Người có khóa riêng có thể tạo chữ ký mang danh tính nhà phát hành, vì vậy cần giới hạn quyền sử dụng.

Các nguyên tắc cần áp dụng:

- Ưu tiên hardware security module, cloud key vault hoặc cơ chế ký từ xa của nhà cung cấp khi phù hợp.
- Nếu dùng certificate file, bảo vệ file và mật khẩu bằng secret store của CI; không commit vào Git.
- Chỉ job phát hành được cấp quyền ký; job build và test thông thường không cần private key.
- Dùng tài khoản runner chuyên dụng với quyền tối thiểu.
- Ghi lại certificate fingerprint, key ID, signer identity, thời điểm ký và artifact digest.
- Có kế hoạch gia hạn, thu hồi và chuyển đổi certificate/key.
- Không in mật khẩu, token, private key hoặc nội dung secret vào log.
- Không dùng khóa phát triển hoặc self-signed certificate cho bản phát hành công khai.

Public key, certificate chain hoặc repository key cần được phân phối qua kênh tin cậy. Nếu người nhận tải public key từ cùng một nơi không được xác thực với package, chuỗi tin cậy có thể bị phá vỡ.

## 6. Windows: ký EXE và MSI bằng Authenticode

### 6.1. Công cụ và certificate

Trên Windows, Microsoft SignTool thuộc Windows SDK. Công cụ này ký, timestamp và xác minh các file hỗ trợ Authenticode, trong đó có EXE, DLL và MSI.

Certificate cần có mục đích Code Signing và private key tương ứng. Certificate có thể được cài trong certificate store của user/machine hoặc được truy cập thông qua provider phần cứng/remote signing mà SignTool hỗ trợ.

Kiểm tra certificate trong store:

~~~powershell
Get-ChildItem Cert:\CurrentUser\My | Select-Object Subject, Thumbprint, NotAfter, HasPrivateKey
~~~

Đảm bảo certificate còn hiệu lực, có private key và đúng danh tính nhà phát hành. Khi cần chọn certificate chính xác trong CI, dùng thumbprint hoặc subject đã được kiểm soát thay vì dựa vào certificate đầu tiên được tìm thấy.

### 6.2. Ký EXE hoặc MSI

Ví dụ ký một file EXE bằng certificate đủ điều kiện trong store:

~~~powershell
signtool sign /a /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 InventoryDesk-Setup.exe
~~~

Ký MSI theo cùng nguyên tắc:

~~~powershell
signtool sign /a /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 InventoryDesk-1.4.0.msi
~~~

Ý nghĩa:

- **/a** tự chọn certificate phù hợp trong store. Với pipeline có nhiều certificate, nên chọn identity cụ thể theo subject hoặc thumbprint.
- **/fd SHA256** chọn digest cho chữ ký file.
- **/tr** dùng RFC 3161 timestamp server.
- **/td SHA256** chọn digest cho timestamp.

SHA-256 và RFC 3161 timestamp là lựa chọn phù hợp cho bản phát hành mới. Không tạo pipeline mới dựa trên SHA-1 hoặc timestamp kiểu cũ chỉ để giữ tương thích với Windows rất cũ không còn nằm trong phạm vi hỗ trợ.

Nếu dùng certificate PFX trong môi trường được kiểm soát, SignTool có thể nhận đường dẫn certificate và mật khẩu qua các tùy chọn tương ứng. Tránh truyền mật khẩu dạng văn bản trong command line hoặc log của CI; ưu tiên certificate store, HSM hoặc secret integration phù hợp.

### 6.3. Xác minh chữ ký Windows

Sau khi ký, xác minh đúng file sẽ phát hành:

~~~powershell
signtool verify /pa /all /v InventoryDesk-Setup.exe
signtool verify /pa /all /v InventoryDesk-1.4.0.msi
~~~

**/pa** dùng chính sách xác minh Authenticode mặc định. **/all** kiểm tra mọi chữ ký nếu file có nhiều chữ ký; **/v** hiển thị thông tin chi tiết.

Có thể xem thông tin chữ ký bằng PowerShell:

~~~powershell
Get-AuthenticodeSignature .\InventoryDesk-Setup.exe | Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
~~~

Chỉ phát hành khi trạng thái là Valid, signer certificate đúng nhà phát hành và timestamp hợp lệ. Exit code của SignTool phải được kiểm tra trong CI; không chỉ tìm dòng chữ “Successfully verified” trong log.

### 6.4. Ký launcher và DLL bên trong application image

Nếu cần ký các executable riêng của ứng dụng trước khi tạo MSI/EXE:

1. Tạo application image trên Windows bằng jpackage.
2. Liệt kê launcher EXE, helper EXE và native DLL do ứng dụng cung cấp.
3. Ký các binary thuộc sản phẩm bằng SignTool.
4. Xác minh từng binary.
5. Tạo installer từ application image đã ký.
6. Ký file MSI/EXE cuối cùng.
7. Xác minh lại installer sau cùng.

Ví dụ ký launcher:

~~~powershell
signtool sign /a /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 build\app-image\InventoryDesk\InventoryDesk.exe
signtool verify /pa /all /v build\app-image\InventoryDesk\InventoryDesk.exe
~~~

Chỉ ký các binary thuộc sản phẩm và thành phần cần ký theo chính sách phát hành. Không thay đổi hoặc ký lại các file runtime của bên thứ ba một cách tùy tiện; giữ nguyên chữ ký nhà cung cấp và kiểm tra tính hợp lệ của chúng.

## 7. jpackage và ký Windows

Man page jpackage JDK 16 không có tùy chọn Windows tương đương **--mac-sign**. Vì vậy, quy trình Windows thông thường tạo package bằng jpackage rồi dùng SignTool để ký EXE/MSI cuối.

Ví dụ tạo MSI:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\input --main-jar inventory-app.jar --main-class com.example.inventory.Main --dest dist
~~~

Sau đó ký và xác minh:

~~~powershell
signtool sign /a /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 dist\InventoryDesk-1.4.0.msi
signtool verify /pa /all /v dist\InventoryDesk-1.4.0.msi
~~~

Nếu cần ký launcher trước khi tạo MSI, hãy tạo app-image trước và ký các binary cần thiết, sau đó gọi jpackage với **--app-image**. Không sửa file bên trong MSI sau khi ký MSI.

## 8. macOS: ký app bundle và installer

### 8.1. Chọn đúng signing identity

Với phân phối trực tiếp ngoài Mac App Store:

- Dùng **Developer ID Application** để ký app bundle, executable, framework và code nhúng.
- Dùng **Developer ID Installer** để ký installer package PKG.
- Nếu phân phối DMG, ký app trước khi đưa vào image. Có thể ký thêm DMG theo chính sách phân phối.

Không dùng Developer ID Installer để ký Mach-O executable hoặc app bundle. Không dùng Developer ID Application để thay cho installer certificate của PKG.

Kiểm tra identity trong Keychain:

~~~bash
security find-identity -v -p codesigning
security find-identity -v
~~~

Lệnh đầu liệt kê identity code signing; lệnh thứ hai giúp kiểm tra cả installer identity. Chọn đúng Team ID và certificate type cho từng artifact.

### 8.2. Ký app bundle

jpackage trên macOS hỗ trợ **--mac-sign**. Ví dụ tạo app image có ký:

~~~bash
jpackage \
  --type app-image \
  --name InventoryDesk \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --mac-package-identifier com.example.inventory \
  --mac-sign \
  --mac-signing-key-user-name "Example Team" \
  --dest build/mac
~~~

Tên identity trong ví dụ phải khớp certificate có trong Keychain. Có thể dùng **--mac-signing-keychain** để chỉ định keychain nếu identity không nằm trong keychain mặc định. Kiểm tra **jpackage --help** của đúng JDK vì tùy chọn và hành vi ký có thể thay đổi theo phiên bản.

Nếu ký bằng codesign bên ngoài, ký nested code trước rồi ký app bundle ngoài cùng. Hoàn tất thay đổi Info.plist, resource, runtime và executable trước khi ký. Không sửa nội dung trong app bundle sau khi đã ký.

### 8.3. Xác minh app bundle

Xác minh chữ ký code:

~~~bash
codesign --verify --deep --strict --verbose=2 build/mac/InventoryDesk.app
~~~

Xem thông tin identity và identifier:

~~~bash
codesign -dv --verbose=4 build/mac/InventoryDesk.app
~~~

**--deep** trong lệnh trên dùng để xác minh code nhúng. Không dùng **codesign --deep** như cách ký toàn bộ ứng dụng phức tạp vì có thể áp cùng entitlement sai cho nhiều thành phần.

### 8.4. Ký PKG và DMG

Với PKG phân phối trực tiếp, ký app bundle bằng Developer ID Application trước, sau đó ký package bằng Developer ID Installer. Có thể dùng jpackage **--mac-sign** nếu JDK và identity phù hợp; nếu cần ký package bên ngoài, dùng productsign:

~~~bash
productsign --sign "Developer ID Installer: Example Team" InventoryDesk-unsigned.pkg InventoryDesk-1.4.0.pkg
~~~

Xác minh chữ ký PKG:

~~~bash
pkgutil --check-signature InventoryDesk-1.4.0.pkg
spctl --assess --type install --verbose=4 InventoryDesk-1.4.0.pkg
~~~

Với DMG, ký app trước khi đưa vào image. Sau khi tạo DMG, ký container nếu kênh phân phối yêu cầu:

~~~bash
codesign --force --sign "Developer ID Application: Example Team" --timestamp InventoryDesk.dmg
hdiutil verify InventoryDesk.dmg
~~~

Không thay đổi nội dung DMG sau khi ký. **hdiutil verify** kiểm tra integrity của disk image; nó không thay thế việc xác minh code signature hoặc notarization.

## 9. Notarization và Gatekeeper trên macOS

Đối với phần mềm Developer ID phân phối trực tiếp, Apple yêu cầu ký hợp lệ, bật Hardened Runtime cho app và command-line target, kèm secure timestamp rồi gửi phần mềm tới notary service.

Notarization khác code signing:

- Code signing xác nhận danh tính ký và tính toàn vẹn.
- Notarization là kiểm tra tự động của Apple trên phần mềm đã ký.
- Stapling gắn ticket notarization vào artifact để Gatekeeper có thể xác minh khi ngoại tuyến.

Apple không còn nhận notarization upload qua **altool** hoặc Xcode 13 trở xuống từ ngày 1/11/2023. Dùng **notarytool** và **stapler** trong quy trình hiện hành.

Gửi DMG:

~~~bash
xcrun notarytool submit InventoryDesk.dmg --keychain-profile "notary-profile" --wait
~~~

Sau khi trạng thái Accepted:

~~~bash
xcrun stapler staple InventoryDesk.dmg
xcrun stapler validate InventoryDesk.dmg
spctl --assess --type execute --verbose=4 InventoryDesk.app
~~~

Nếu phân phối PKG, gửi PKG tới notary service, staple ticket vào PKG và xác minh bằng **pkgutil**, **stapler** và **spctl**. Kiểm tra log notarization nếu Apple trả về Invalid; không phát hành artifact bị từ chối.

Notarization không phải yêu cầu riêng cho ứng dụng tải từ Mac App Store vì quy trình App Store có bước xác minh riêng. Không dùng Developer ID distribution workflow thay cho quy trình App Store signing.

## 10. Linux RPM: ký trực tiếp package bằng OpenPGP

### 10.1. Tạo và quản lý khóa ký RPM

RPM package có thể chứa chữ ký OpenPGP. Nhà phát hành cần có khóa riêng để ký và phân phối public key/fingerprint qua kênh tin cậy cho người cài đặt.

Khóa riêng nên được bảo vệ bằng GPG agent, smartcard, HSM hoặc cơ chế quản lý khóa tương đương. Không đặt private key trong source repository hoặc trong image ứng dụng.

Trước khi ký, kiểm tra khóa:

~~~bash
gpg --list-secret-keys --keyid-format LONG
gpg --fingerprint KEY_ID
~~~

So sánh fingerprint với giá trị đã công bố trong quy trình phát hành. Không chỉ dựa vào tên UID vì tên hiển thị có thể trùng.

### 10.2. Ký RPM

Sau khi tạo package bằng jpackage, dùng rpmsign:

~~~bash
rpmsign --addsign dist/inventory-desk-1.4.0-1.x86_64.rpm
~~~

rpmsign lấy cấu hình GPG signing từ cấu hình RPM của người dùng hoặc môi trường build. Cấu hình key ID, GPG path và signing command theo phiên bản RPM trên runner. Thực hiện trong tài khoản chuyên dụng có quyền sử dụng khóa ký.

**--addsign** thêm chữ ký cho package. **--resign** thay thế chữ ký hiện có; chỉ dùng khi chủ động ký lại artifact. Không dùng thao tác xóa chữ ký hoặc ký lại để che giấu lỗi xác minh.

### 10.3. Xác minh RPM

Xác minh chữ ký và checksum:

~~~bash
rpm --checksig --verbose dist/inventory-desk-1.4.0-1.x86_64.rpm
~~~

Kết quả cần cho thấy digest hợp lệ và chữ ký được xác minh bằng khóa tin cậy. Một package có digest đúng nhưng chữ ký là **NOKEY** chưa chứng minh signer đáng tin cậy; cần import public key đúng qua kênh tin cậy rồi xác minh lại.

Kiểm tra metadata package:

~~~bash
rpm -qp --qf '%{NAME} %{VERSION}-%{RELEASE}\n' dist/inventory-desk-1.4.0-1.x86_64.rpm
rpm -qpl dist/inventory-desk-1.4.0-1.x86_64.rpm
~~~

Chỉ đưa package vào repository sau khi chữ ký package đã được xác minh. Nếu repository cũng ký metadata, tiếp tục thực hiện bước ký repository.

## 11. Linux RPM repository: ký metadata riêng

Khi phân phối RPM qua repository, có thể có hai lớp xác thực:

1. Chữ ký OpenPGP gắn trực tiếp vào từng RPM package.
2. Chữ ký metadata repository, thường là **repomd.xml**, để package manager xác thực metadata và checksum package.

Ví dụ sau khi đã tạo repository metadata:

~~~bash
gpg --armor --detach-sign --output repodata/repomd.xml.asc repodata/repomd.xml
~~~

Repository client cần được cấu hình xác minh metadata và package, ví dụ với DNF:

~~~ini
[inventory]
name=Inventory Application
baseurl=https://packages.example.com/rpm/
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://packages.example.com/keys/RPM-GPG-KEY-inventory
~~~

**gpgcheck=1** yêu cầu xác minh chữ ký package; **repo_gpgcheck=1** yêu cầu xác minh metadata repository. Tên khóa, URL và chính sách phải được thiết lập đúng với bản phân phối và công cụ quản lý package đích.

Nếu nội dung repository thay đổi, phải tạo lại metadata và ký lại metadata mới. Không sửa repomd.xml sau khi ký.

## 12. Linux DEB: xác thực repository APT

### 12.1. Hiểu đúng mô hình chữ ký APT

APT thông thường không xác minh chữ ký OpenPGP nhúng trong từng file DEB. Chuỗi tin cậy của APT dựa trên:

1. Repository có file **InRelease** hoặc cặp **Release** và **Release.gpg**.
2. File Release được ký bằng khóa archive/repository.
3. Release chứa checksum của các file Packages.
4. Packages metadata chứa checksum của file DEB.
5. APT kiểm tra chữ ký metadata và checksum khi tải/cài package.

Nhờ vậy, APT phát hiện package hoặc metadata bị thay đổi trên đường truyền hoặc trên mirror. Tin cậy repository có nghĩa người dùng tin cậy nhà duy trì repository; nó không chứng minh package không có mã độc.

### 12.2. Tạo và ký repository metadata

Ví dụ sau khi đã sắp xếp DEB và tạo Packages metadata theo cấu trúc repository:

~~~bash
apt-ftparchive release dists/stable > dists/stable/Release
gpg --clearsign --output dists/stable/InRelease dists/stable/Release
gpg --armor --detach-sign --output dists/stable/Release.gpg dists/stable/Release
~~~

Public key của repository phải được phân phối qua kênh tin cậy và giới hạn phạm vi bằng cấu hình **Signed-By** trong source entry của APT. Không dùng **apt-key** cho quy trình mới; quản lý keyring riêng và chỉ gắn khóa cho repository tương ứng.

Ví dụ source entry:

~~~text
Types: deb
URIs: https://packages.example.com/debian
Suites: stable
Components: main
Signed-By: /etc/apt/keyrings/inventory-archive.gpg
~~~

### 12.3. Xác minh APT repository

Có thể kiểm tra chữ ký Release bằng GPG:

~~~bash
gpgv --keyring /etc/apt/keyrings/inventory-archive.gpg dists/stable/InRelease
~~~

Hoặc xác minh chữ ký detached:

~~~bash
gpgv --keyring /etc/apt/keyrings/inventory-archive.gpg dists/stable/Release.gpg dists/stable/Release
~~~

Sau đó kiểm tra bằng chính APT trên môi trường client thử nghiệm:

~~~bash
sudo apt update
apt-cache policy inventory-desk
~~~

APT tự xác minh Release signature và checksum khi cập nhật repository. Nếu chữ ký sai, khóa không được tin cậy hoặc checksum không khớp, không bỏ qua lỗi bằng cách bật tùy chọn cho phép repository không an toàn.

### 12.4. Khi nào cần chữ ký gắn trực tiếp trên DEB?

Nếu phân phối một file DEB độc lập ngoài repository APT, có thể cần cơ chế xác minh riêng theo chính sách tổ chức. **debsig-verify** dùng để xác minh chữ ký package theo policy đã cấu hình; **debsign** thường ký tệp .changes trong quy trình upload package. Công cụ bên thứ ba **dpkg-sig** cũng có thể tạo/xác minh chữ ký trên archive DEB.

Ví dụ xác minh package-level signature khi hệ thống đã cài công cụ và cấu hình policy/keyring tương ứng:

~~~bash
debsig-verify inventory-desk_1.4.0-1_amd64.deb
dpkg-sig --verify inventory-desk_1.4.0-1_amd64.deb
~~~

Đây không phải cơ chế xác minh package mặc định của APT. Người nhận phải cài đặt và cấu hình công cụ/keyring tương ứng để kiểm tra chữ ký đó. Không mô tả dpkg-sig như một phần thay thế cho chữ ký InRelease/Release.gpg của repository.

## 13. Kiểm tra artifact sau khi ký

Sau bước ký, xác minh từng loại file bằng công cụ tương ứng:

| Nền tảng | Artifact | Kiểm tra |
|---|---|---|
| Windows | EXE/MSI | signtool verify /pa /all /v file |
| macOS | App bundle | codesign --verify --deep --strict --verbose=2 App.app |
| macOS | PKG | pkgutil --check-signature file.pkg |
| macOS | App/installer policy | spctl --assess với type phù hợp |
| macOS | DMG | hdiutil verify file.dmg và kiểm tra chữ ký/notarization nếu yêu cầu |
| macOS | Notarization ticket | xcrun stapler validate file |
| RPM | Package | rpm --checksig --verbose file.rpm |
| APT | Repository | gpgv trên InRelease hoặc Release.gpg, sau đó apt update |

Không dùng một công cụ chung để xác minh mọi loại file. **sha256sum** hoặc **Get-FileHash** chỉ kiểm tra digest; nếu không có digest được lấy từ nguồn tin cậy, chúng không xác thực nhà phát hành.

## 14. Xác minh danh tính, timestamp và chuỗi tin cậy

Chữ ký hợp lệ về mặt toán học chưa đủ. Pipeline cần xác minh:

- Signer subject hoặc Team ID khớp nhà phát hành mong đợi.
- Certificate chain được hệ điều hành tin cậy.
- Certificate chưa bị thu hồi tại thời điểm xác minh theo chính sách.
- Timestamp được tạo bởi timestamp authority tin cậy.
- Digest algorithm đáp ứng yêu cầu hiện hành.
- Package signature hoặc repository signature khớp public key đã được pin/phân phối tin cậy.
- Artifact digest sau ký khớp với file được upload.

Windows: xem SignerCertificate và TimeStamperCertificate từ kết quả SignTool/Authenticode. macOS: xem authority, Team ID, identifier và kết quả Gatekeeper/notarization. RPM/APT: xác minh đúng key fingerprint, không chỉ dựa vào tên UID.

Nếu certificate đã hết hạn, timestamp hợp lệ có thể giúp hệ điều hành đánh giá chữ ký theo thời điểm ký. Tuy nhiên, timestamp không khắc phục certificate bị thu hồi hoặc chữ ký sai. Hãy xử lý certificate hết hạn/thu hồi theo chính sách của CA và nền tảng.

## 15. Tạo checksum sau khi ký

Sau khi ký và xác minh thành công, tạo checksum cho đúng artifact cuối cùng:

Windows PowerShell:

~~~powershell
Get-FileHash .\dist\InventoryDesk-1.4.0.msi -Algorithm SHA256
~~~

macOS/Linux:

~~~bash
shasum -a 256 dist/InventoryDesk-1.4.0.pkg
sha256sum dist/inventory-desk-1.4.0-1.x86_64.rpm
~~~

Đối với DEB:

~~~bash
sha256sum dist/inventory-desk_1.4.0-1_amd64.deb
~~~

Checksum giúp phát hiện file tải xuống không giống artifact đã công bố khi người nhận lấy checksum từ một kênh tin cậy. Checksum không thay thế chữ ký số và không chứng minh nguồn phát hành nếu checksum được phân phối cùng một nguồn không đáng tin cậy.

## 16. Pipeline CI đề xuất

Một pipeline phát hành có thể chia thành các job:

1. **Build:** compile, test và tạo JAR/runtime.
2. **Package:** chạy jpackage trên runner đúng OS/architecture.
3. **Inner-code signing:** ký executable/native library của ứng dụng nếu chính sách yêu cầu.
4. **Installer signing:** ký EXE/MSI, PKG hoặc RPM; với DEB, tạo repository metadata và ký Release khi phát hành qua APT.
5. **Verification:** kiểm tra chữ ký, identity, timestamp, notarization và metadata.
6. **Install test:** cài trên máy/VM sạch và chạy smoke test.
7. **Checksum:** tạo checksum sau khi ký và xác minh.
8. **Publish:** chỉ upload artifact đã qua tất cả bước kiểm tra.

Ví dụ điều kiện phát hành:

~~~text
if package_build_failed:
    stop
if signing_failed:
    stop
if signature_verification_failed:
    stop
if signer_identity_mismatch:
    stop
if timestamp_or_notarization_required_but_missing:
    stop
if clean_install_test_failed:
    stop
publish_verified_artifact()
~~~

Giữ log xác minh, certificate fingerprint/key ID, phiên bản JDK/SDK, checksum và build provenance cùng bản phát hành. Không lưu private key hoặc secret trong artifact/log.

## 17. Kiểm thử trên máy sạch

Máy build có thể đã tin cậy certificate hoặc public key mà máy người dùng chưa có. Vì vậy, cần thử cài đặt trên môi trường gần với người nhận:

- Windows: VM Windows sạch, certificate chain có thể kiểm tra, xác nhận publisher trong UAC/installer và thử cài/gỡ.
- macOS: VM hoặc máy Mac sạch có Gatekeeper bật, kiểm tra notarization, stapled ticket và mở app lần đầu.
- RPM: máy hoặc container của bản phân phối mục tiêu có public key đã cài đúng, thử cài qua DNF và xác minh package.
- APT: client sạch chỉ có keyring repository đã công bố, chạy apt update, cài package và xác minh không có cảnh báo chữ ký.

Kiểm tra cả trường hợp thiếu khóa, khóa sai, package bị thay đổi và timestamp/notarization bị thiếu. Pipeline cần từ chối các trường hợp này thay vì tự động bỏ qua kiểm tra.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SignTool không tìm thấy certificate | Certificate/private key không nằm trong store hoặc tài khoản runner không truy cập được | Kiểm tra certificate store, private key và identity được chọn. |
| Windows báo chữ ký không hợp lệ sau khi ký | File bị sửa sau ký hoặc timestamp/signing command lỗi | Tạo lại artifact, ký lại và xác minh file cuối. |
| Windows verify được nhưng publisher sai | Pipeline tự chọn nhầm certificate | Chọn identity theo thumbprint/subject và kiểm tra signer trong CI. |
| PKG không có chữ ký tin cậy | Dùng Developer ID Application thay cho Developer ID Installer | Ký PKG bằng installer identity đúng. |
| macOS notarization bị từ chối | Code chưa ký đầy đủ, thiếu Hardened Runtime/timestamp hoặc dùng certificate sai | Đọc notary log, sửa nested code signing và gửi lại. |
| RPM trả về NOKEY | Client chưa tin cậy public key ký RPM | Phân phối fingerprint/public key qua kênh tin cậy rồi import và verify lại. |
| RPM digest OK nhưng signature fail | Package bị thay đổi hoặc chữ ký không hợp lệ | Tạo lại package từ artifact gốc và ký lại bằng khóa đúng. |
| APT báo repository không được xác thực | InRelease/Release.gpg thiếu, sai chữ ký hoặc client chưa có key tin cậy | Kiểm tra Release metadata, keyring và Signed-By. |
| APT update được nhưng package file bị đổi | Checksum metadata không được cập nhật hoặc repository không được ký lại | Tạo lại Packages/Release, ký lại InRelease và Release.gpg. |
| DEB có file nhưng APT không nhận chữ ký riêng | Nhầm chữ ký package với chữ ký repository | Dùng APT Release signature; chỉ dùng package-level signature nếu client được cấu hình công cụ riêng. |
| Chữ ký đúng nhưng checksum công bố sai | Tạo checksum trước khi ký hoặc checksum lấy từ artifact khác | Tạo checksum sau khi ký và xác minh trên đúng file publish. |

## 19. Checklist trước khi phát hành

- [ ] Build package trên runner đúng nền tảng và kiến trúc.
- [ ] Kiểm tra application image và installer trước khi ký.
- [ ] Dùng certificate/key chính thức của nhà phát hành.
- [ ] Bảo vệ private key bằng secret store/HSM/keychain.
- [ ] Ký code bên trong trước khi ký container ngoài nếu nền tảng yêu cầu.
- [ ] Ký installer/package hoặc repository metadata đúng mô hình nền tảng.
- [ ] Dùng SHA-256 và timestamp phù hợp cho Authenticode.
- [ ] Bật Hardened Runtime, ký Developer ID và notarize khi phân phối trực tiếp trên macOS.
- [ ] Kiểm tra RPM signature hoặc APT repository signature bằng đúng public key.
- [ ] Xác minh signer identity, certificate chain, timestamp và tính toàn vẹn.
- [ ] Kiểm thử cài đặt trên môi trường sạch.
- [ ] Tạo checksum sau khi ký và xác minh.
- [ ] Chỉ publish artifact đã được xác minh.
- [ ] Lưu log, fingerprint, checksum và provenance; không lưu secret.

## 20. Cách áp dụng trong quy trình Java hiện đại

- Xem jpackage là bước tạo native package; thực hiện signing bằng công cụ nền tảng nếu jpackage không cung cấp tùy chọn tương ứng.
- Trên Windows, dùng SignTool để ký EXE/MSI bằng SHA-256 và RFC 3161 timestamp; xác minh bằng Authenticode policy.
- Trên macOS, ký app bằng Developer ID Application, ký PKG bằng Developer ID Installer, dùng notarytool/stapler cho phân phối trực tiếp và kiểm tra Gatekeeper.
- Trên RPM, ký package bằng rpmsign và xác minh bằng rpm --checksig; nếu có repository, ký cả metadata repository.
- Với DEB, ưu tiên mô hình APT repository có InRelease hoặc Release.gpg được ký; phân biệt rõ với chữ ký package-level tùy chọn.
- Quản lý public key, certificate fingerprint và key rotation qua kênh tin cậy.
- Không sửa artifact sau khi ký; xác minh rồi mới tạo checksum và publish.
- Dùng runner/VM sạch để xác nhận người nhận thực sự có thể xác minh và cài đặt.

Ký package là một phần của quy trình phát hành có thể kiểm chứng. Mỗi nền tảng có mô hình tin cậy riêng, vì vậy cần dùng đúng danh tính, đúng công cụ và đúng lệnh xác minh cho từng artifact. Khi CI kiểm tra được chữ ký, signer, timestamp, repository metadata và cài đặt thực tế trước khi publish, người nhận có cơ sở xác thực nguồn phát hành và phát hiện package bị thay đổi.

## Tài liệu tham khảo

- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle JDK 24 — The jpackage Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html)
- [Microsoft Learn — SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)
- [Microsoft Learn — Time Stamping Authenticode Signatures](https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures)
- [Microsoft Learn — Use SignTool to Sign a File](https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-sign-a-file)
- [Apple — Notarizing macOS Software Before Distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Apple — Resolving Common Notarization Issues](https://developer.apple.com/documentation/security/resolving-common-notarization-issues)
- [RPM — rpmsign Manual](https://rpm.org/docs/6.0.x/man/rpmsign.1)
- [Debian — apt-secure Manual](https://manpages.debian.org/trixie/apt/apt-secure.8.en.html)
- [Debian — dpkg-sig Manual](https://manpages.debian.org/unstable/dpkg-sig/dpkg-sig.1.en.html)
