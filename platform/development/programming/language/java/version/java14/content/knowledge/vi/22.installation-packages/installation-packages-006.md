# Ký gói cài đặt và xác minh theo yêu cầu của từng nền tảng

> **Ngữ cảnh:** Java 14 → **Gói cài đặt** → **Ký gói và xác minh theo yêu cầu của nền tảng**. `jpackage` từng là công cụ *incubating* ở Java 14/15, nhưng đã trở thành công cụ đóng gói chính thức từ **Java 16 (JEP 392)**. Trong các JDK hiện hành, công cụ có thể tạo `app-image` và gói `exe`/`msi` (Windows), `dmg`/`pkg` (macOS), `deb`/`rpm` (Linux). **Ký và xác minh không phải một cơ chế giống nhau trên mọi hệ điều hành.** Bài này chỉ dùng công cụ và quy trình hiện còn áp dụng, không hướng dẫn `jdk.incubator.jpackage`, Apple `altool` cũ, SHA-1 làm thuật toán ký mới, hay cấu hình bỏ qua kiểm tra chữ ký.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt **đóng gói**, **ký số**, **xác minh chữ ký**, **kiểm tra nguồn tin cậy**, **notarization**, **timestamp** và **checksum**.
2. Xác định chính xác **artifact nào cần ký**: launcher, ứng dụng `.app`, installer `.exe`/`.msi`/`.pkg`, RPM hoặc metadata repository.
3. Nêu vai trò của `jpackage`: trên macOS có `--mac-sign`; trên Windows, việc ký Authenticode thông thường là **bước riêng** bằng SignTool/dịch vụ ký; trên Linux theo hệ sinh thái RPM/APT.
4. Thực hiện đúng quy trình Windows: build → ký bằng chứng thư code-signing tin cậy và SHA-256 → gắn RFC 3161 timestamp → `signtool verify` → kiểm thử cài đặt.
5. Thực hiện đúng quy trình macOS: ký ứng dụng bằng **Developer ID** khi phân phối ngoài Mac App Store → gửi Apple **`notarytool`** → nhận kết quả **Accepted** → **staple** ticket → xác minh Gatekeeper và chạy thử.
6. Phân biệt chữ ký OpenPGP trên RPM với mô hình xác thực **`InRelease`/`Release`** của kho APT chứa `.deb`.
7. Dùng SHA-256 để kiểm tra tính toàn vẹn nhưng **không nhầm checksum với chứng cứ về nhà phát hành**.
8. Lập checklist cho CI/CD: chứng chỉ, khóa bí mật, ký sau build, verify trên máy sạch, nguồn phân phối, cập nhật và quản lý sự cố.
9. Biết kiểm thử bằng các ví dụ Java 17 độc lập, đồng thời không giả vờ rằng có thể ký thật trên mọi OS khi chưa có tài khoản nhà phát hành và khóa hợp lệ.

## 2. Vì sao “`jpackage` đã thành công” chưa đủ để phát hành?

Ví dụ công cụ chạy thành công:

~~~bash
jpackage --type app-image --name ExampleDesk --input input --main-jar app.jar --dest build
~~~

Đây là **lệnh minh họa**, giả định `input/app.jar` đã tồn tại và có điểm khởi chạy. Lệnh tạo **application image**, tức bundle có launcher, ứng dụng và Java runtime được chuẩn bị để chạy. Nó **không tự chứng minh** launcher hoặc gói cài đặt đã được ký bằng danh tính nhà phát hành tin cậy.

Sự khác nhau:

| Khâu | Câu hỏi cần trả lời | Công cụ điển hình |
| --- | --- | --- |
| **Build/packaging** | Artifact có đủ mã và runtime để chạy không? | `javac`, `jar`, `jlink`, `jpackage` |
| **Hash/digest** | Bytes có trùng đúng một bản tham chiếu không? | SHA-256, `sha256sum`, `Get-FileHash` |
| **Digital signature** | Nội dung đã ký có bị sửa và có liên hệ tới public key nào? | Authenticode, Apple Code Signing, OpenPGP |
| **Identity/trust** | Public key/chứng chỉ có được nền tảng hoặc repository policy tin cậy không? | Certificate chain, CA, keyring, repository trust |
| **Timestamp** | Chữ ký được xác nhận tại thời điểm nào? | RFC 3161 TSA trên Windows; thời điểm ký/notary theo hệ sinh thái |
| **Notarization** | Apple đã kiểm tra và cấp ticket cho phần mềm phân phối ngoài Store chưa? | `xcrun notarytool`, `xcrun stapler` |
| **OS policy** | Máy đích có cho phép tải/cài/chạy ứng dụng không? | SmartScreen/Smart App Control, Gatekeeper, RPM/APT trust |
| **Functional test** | Bundle được ký có thực sự cài và chạy không? | Smoke tests trên máy/VM sạch |

**Chữ ký hợp lệ không đồng nghĩa phần mềm an toàn tuyệt đối.** Chữ ký giúp xác định integrity và danh tính/key trong một cơ chế tin cậy; nó không chứng minh code không có bug hoặc malware. Các hệ điều hành còn có reputation, revocation, policy doanh nghiệp và cơ chế chống mã độc độc lập.

**Checksum tự công bố một mình cũng chưa xác minh nhà phát hành.** Kẻ tấn công có quyền thay đồng thời file tải và chuỗi checksum trên cùng trang có thể tạo một cặp khớp giả. Muốn tăng độ tin cậy cần nguồn checksum có xác thực, chữ ký hoặc kênh phát hành được bảo vệ.

## 3. Bản đồ công cụ theo nền tảng

| Hệ điều hành | `jpackage --type` | Cơ chế ký/kiểm tra chủ yếu | Điểm cần chú ý |
| --- | --- | --- | --- |
| **Windows** | `exe`, `msi`, `app-image` | **Authenticode** qua `signtool` hoặc dịch vụ ký; `signtool verify /pa` | JDK 25 `jpackage` không có cờ ký Windows tương đương `--mac-sign`. |
| **macOS** | `dmg`, `pkg`, `app-image` | **Apple Code Signing**, `--mac-sign`; **Developer ID**, **notarytool**, **stapler**, Gatekeeper | Ký khác notarization; từng loại artifact phải được xác minh thích hợp. |
| **RPM Linux** | `rpm`, `app-image` | Chữ ký **OpenPGP** trên RPM; `rpmsign`, `rpmkeys --checksig` | Cần public key đã được tin cậy, không chỉ kiểm tra “có signature”. |
| **Debian/Ubuntu** | `deb`, `app-image` | **APT repository `InRelease` được ký**, liên kết tới hash các gói | `dpkg -i` một file `.deb` riêng **không mặc nhiên xác minh repo signature**. |

Một số điều kiện nền tảng không thể đảo ngược:

- **`jpackage` xây gói native trên hệ điều hành đích.** Muốn tạo `.msi` cho Windows, chạy trên Windows với toolchain phù hợp; `.dmg` trên macOS; `.rpm`/`.deb` trên Linux.
- Đóng gói ở một OS rồi copy sang OS khác **không biến launcher thành binary native cho OS mới**.
- Môi trường CI cần cả JDK thích hợp và công cụ cài đặt/chứng thư của nền tảng.
- Chỉ chạy `jpackage --help` trên OS hiện tại sẽ hiện những option phù hợp nền tảng đó; không suy ra cờ macOS tồn tại trên Windows.

Các bước ký và xác minh **khác nhau theo loại artifact**, vì thế không nên viết một script “sign-anything” rồi giả định kết quả giống nhau.

## 4. Quy trình phát hành tổng quát

Pipeline đề xuất:

~~~text
Source đã review + dependency đã kiểm soát
          |
          v
Biên dịch / test / tạo JAR, module
          |
          v
jpackage trên OS đích
          |
          v
Smoke-test artifact CHƯA ký
          |
          v
Ký artifact và/hoặc payload theo chính sách OS
          |
          v
Xác minh chữ ký + chain/identity + timestamp
          |
          v
macOS: notarize -> Accepted -> staple -> verify
Linux: ký RPM hoặc publish trong repo APT có InRelease ký
          |
          v
Tạo SHA-256 manifest của ARTIFACT CUỐI CÙNG
          |
          v
Kiểm thử cài, nâng cấp, gỡ và khởi chạy trên máy sạch
          |
          v
Phát hành qua kênh được kiểm soát và lưu audit evidence
~~~

**Không thay đổi bytes một cách tùy tiện sau khi ký.** Các bước như chèn file, thay icon, sửa `Info.plist`, thay launcher, ghép resource hoặc chỉnh installer sau chữ ký có thể làm hỏng chữ ký. **Stapling** ticket notarization có thể làm thay đổi bytes file phân phối; do đó tạo/checksum manifest **sau bước cuối cùng làm thay đổi artifact**.

Khi CI cần reproducible build, hãy lưu cả **hash bản trước ký** (để điều tra quy trình) và **hash bản phát hành cuối** (để người nhận xác minh); hai hash **không nhất thiết giống nhau**, bởi chữ ký/timestamp/notary ticket thêm metadata.

## 5. Windows: ký Authenticode bằng SignTool

### 5.1. Điểm vào `jpackage`

Trên Windows, công cụ có thể tạo `.exe` hoặc `.msi`; ví dụ có input JAR:

~~~powershell
jpackage --type msi --name ExampleDesk --app-version 1.0 --input input --main-jar app.jar --dest dist
~~~

Đây là **mẫu lệnh đóng gói**, cần có `input/app.jar` hợp lệ và toolchain Windows cần thiết (Windows SDK/installer tools theo bản JDK và loại gói). Hãy kiểm tra chính xác **tên file MSI được tạo trong `dist`**, vì naming/version/architecture có thể khác kỳ vọng.

**Không giả định MSI được tạo đã ký.** Tài liệu `jpackage` JDK 25 có `--mac-sign` riêng cho macOS, nhưng **không cung cấp tùy chọn ký Windows** tương đương. Trên Windows, bạn cần bước ký số bên ngoài `jpackage`.

### 5.2. Chuẩn bị danh tính ký

Để ký phát hành ra công chúng, dùng chứng thư **code-signing** có chuỗi tin cậy phù hợp với Windows, khóa riêng được quản lý an toàn (hardware token/HSM/cloud signing theo chính sách). Microsoft hỗ trợ những lựa chọn như chứng thư từ CA phù hợp hoặc **Artifact Signing** (tên hiện hành của dịch vụ từng gọi Trusted Signing), tùy quốc gia và điều kiện tài khoản.

Không lưu file PFX chứa private key kèm password trong Git repository. Trong CI, dùng secret manager/HSM hoặc dịch vụ ký, giới hạn quyền thao tác, ghi audit trail và áp chính sách rotation/revocation.

**Lưu ý:** self-signed certificate thích hợp cho thử nghiệm nội bộ có quản lý trust, **không mặc nhiên được người dùng Internet tin cậy**. Chỉ thay lựa chọn chứng thư khi đã kiểm tra tiêu chí phân phối, không bỏ qua cảnh báo hệ điều hành.

### 5.3. Ký file đã đóng gói

Microsoft **SignTool** là công cụ thuộc Windows SDK. Nếu máy ký có chứng thư phù hợp trong certificate store, một **mẫu lệnh trên máy ký Windows**:

~~~powershell
signtool sign /a /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 "dist\ExampleDesk-1.0.msi"
~~~

Giải thích:

- `sign`: yêu cầu tạo chữ ký Authenticode.
- `/a`: chọn tự động chứng thư phù hợp trong store. **Với CI production có nhiều identity, nên chọn chính xác chứng thư theo thumbprint/identity chính sách**, tránh ký nhầm danh tính.
- `/fd SHA256`: hash algorithm của file khi ký; sử dụng SHA-256 thay vì SHA-1 cũ cho phát hành mới.
- `/tr`: URL máy chủ timestamp theo **RFC 3161**, cần dùng TSA tin cậy thật sự.
- `/td SHA256`: hash algorithm của RFC 3161 timestamp.
- Đường dẫn MSI phải được **thay bằng file thực sự đã build**, nếu tên khác; lệnh chỉ thành công khi chứng thư, khóa riêng, mạng và SignTool đã được cấu hình.

Đây **không phải thao tác không cần điều kiện**: thiếu chứng thư/khóa/timestamp server khiến lệnh thất bại. Không được báo đã ký thành công chỉ vì bạn có thể chạy `jpackage` hoặc `signtool --help`.

Để ký executable launcher `.exe` hoặc thành phần code khác theo yêu cầu Smart App Control/chính sách khách hàng, ký các binary cần thiết trước khi đóng installer hoặc dùng một pipeline tạo app image → ký binary → dùng app image đó xây installer. **Chữ ký trên một MSI không tự thay thế mọi yêu cầu ký của tất cả executable nằm trong nó.**

### 5.4. Xác minh Authenticode

Sau ký, thực hiện:

~~~powershell
signtool verify /pa /v "dist\ExampleDesk-1.0.msi"
~~~

Trong đó `/pa` dùng **Default Authenticode Verification Policy**. Xem exit code, thông tin publisher, chain và timestamp, không chỉ kiểm tra rằng tool đã in vài dòng.

Một phép kiểm tra bổ sung bằng PowerShell:

~~~powershell
$signature = Get-AuthenticodeSignature -FilePath "dist\ExampleDesk-1.0.msi"
$signature.Status
$signature.SignerCertificate.Subject
~~~

`Status` thường cần là `Valid` trong ngữ cảnh trust mong đợi; phải kiểm tra certificate identity đúng tổ chức. Nếu có trạng thái như `NotSigned`, `UnknownError` hoặc `NotTrusted`, **không phát hành** trước khi điều tra.

**Đừng chỉ kiểm tra chữ ký rồi bỏ qua installer test.** Test thêm cài đặt, nâng cấp, uninstall và mở launcher trên một Windows sạch với policy thực tế. Một bộ cài có chữ ký hợp lệ vẫn có thể lỗi dependency, quyền truy cập hoặc upgrade GUID.

### 5.5. Timestamp và SmartScreen

Theo Microsoft, chữ ký Authenticode có **RFC 3161 timestamp** giúp bằng chứng thời điểm ký và có vai trò quan trọng khi chứng thư code-signing hết hạn. Với phát hành mới, nên ký SHA-256 và timestamp SHA-256 như trên. Không dùng `/t` kiểu timestamp cũ hoặc ký SHA-1-only để làm mặc định.

**Ký hợp lệ không bảo đảm Windows SmartScreen sẽ không cảnh báo.** SmartScreen có cơ chế reputation của file hash và publisher, nên bản phát hành/chứng thư mới có thể bị đánh giá là chưa có reputation; chính sách enterprise còn có thể nghiêm hơn. **EV certificate không còn bảo đảm bỏ qua cảnh báo SmartScreen ngay lập tức** theo hướng dẫn Microsoft hiện hành. Không bảo người dùng tắt SmartScreen để vượt lỗi ký; cần làm đúng code signing, kênh phân phối và kiểm tra kết quả trên máy đích.

## 6. macOS: `jpackage --mac-sign`, Developer ID và notarization

### 6.1. Chọn đúng loại chứng thư

Khi phân phối **ngoài Mac App Store**, Apple yêu cầu dùng danh tính **Developer ID** phù hợp với loại thành phần:

- **Developer ID Application**: ký mã ứng dụng, executable và bundle `.app`.
- **Developer ID Installer**: ký installer dạng `.pkg`.
- Cần thỏa các yêu cầu về **hardened runtime**, entitlements và cấu trúc bundle để Apple notarization có thể chấp nhận.
- Với **Mac App Store**, signing/submission theo bộ chứng thư và workflow riêng, không dùng quy trình Developer ID bên ngoài Store như một phương án thay thế.

Để xem code-signing identities mà máy Mac có thể dùng:

~~~bash
security find-identity -v -p codesigning
~~~

Danh sách không có chứng thư đúng là lỗi chuẩn bị môi trường. Công cụ không tự sinh ra một Developer ID production hợp lệ.

### 6.2. Ký với `jpackage`

Trên **máy macOS**, ví dụ ứng dụng JAR có điểm vào:

~~~bash
jpackage --type dmg --name ExampleDesk --app-version 1.0 --input input --main-jar app.jar --dest dist --mac-package-identifier com.example.exampledesk --mac-sign --mac-signing-key-user-name "Example Team"
~~~

Đây là **mẫu quy trình**, trong đó `"Example Team"` phải được **thay bằng tên user/team đúng với Apple signing identity đã cài**, và `com.example.exampledesk` phải là identifier thật của ứng dụng. Nếu `input/app.jar`, chứng thư hoặc điều kiện signing chưa có thì lệnh **không thể hoàn tất** như một lệnh copy-paste vô điều kiện.

Ý nghĩa option:

| Tùy chọn | Tác dụng |
| --- | --- |
| `--type dmg` | Tạo disk image để phân phối trên macOS. |
| `--type pkg` | Tạo installer package dạng `.pkg` nếu chọn dạng này thay `dmg`. |
| `--mac-sign` | Yêu cầu `jpackage` ký bundle/package trên macOS. |
| `--mac-signing-key-user-name` | Phần user/team trong tên chứng thư Apple để chọn identity. |
| `--mac-signing-keychain` | Tùy chọn chỉ ra keychain không mặc định chứa signing identity. |
| `--mac-package-identifier` | Identifier của ứng dụng, cần ổn định/duy nhất. |
| `--mac-package-signing-prefix` | Prefix cho thành phần cần ký khi chúng thiếu package identifier riêng. |
| `--mac-entitlements` | File entitlements nếu ứng dụng cần quyền/cấu hình runtime cụ thể. |
| `--mac-app-store` | Chế độ cho Mac App Store; không dùng thay cho Developer ID distribution. |

Tài liệu `jpackage` còn hỗ trợ ký một **app image đã tạo** trên macOS bằng `--app-image` cùng `--mac-sign` và các tùy chọn liên quan. Khi đổi resource hoặc app bundle sau khi ký, phải **ký/xác minh lại** theo pipeline được phê duyệt.

### 6.3. Xác minh chữ ký ứng dụng trước notarization

Với app bundle đã được tạo từ `jpackage`, kiểm tra trên macOS:

~~~bash
codesign --verify --strict --verbose=2 "/Applications/ExampleDesk.app"
codesign --display --verbose=4 "/Applications/ExampleDesk.app"
~~~

Đường dẫn ứng dụng ở trên là **ví dụ**: nếu chưa cài app, thay bằng đường dẫn tới `.app` thực tế trong app image hoặc disk image đã mount. Hãy xem TeamIdentifier, signing authority và entitlements theo chính sách; `codesign` thành công chứng minh chữ ký đã kiểm tra ở mức công cụ, **không tự chứng minh notarization đã Accepted**.

Có thể kiểm tra đánh giá Gatekeeper:

~~~bash
spctl --assess --type execute --verbose=4 "/Applications/ExampleDesk.app"
~~~

Hành vi còn phụ thuộc quarantine attribute, Gatekeeper policy và máy kiểm thử. Dùng một máy hoặc VM macOS sạch để kiểm chứng trải nghiệm thực sự của người dùng khi tải/gắn disk image và mở ứng dụng.

Với file `.pkg`, có thể kiểm tra chữ ký installer qua:

~~~bash
pkgutil --check-signature "dist/ExampleDesk-1.0.pkg"
~~~

Không dùng `pkgutil --check-signature` để xác minh một file `.dmg` như thể nó là `.pkg`; mỗi tool/kiểu artifact có chức năng khác nhau.

### 6.4. Notarization không giống code signing

Đối với software phân phối bằng Developer ID ngoài Store, Apple có **notarization service** để kiểm tra bundle, phát hiện các vấn đề về ký và quét nội dung theo chính sách. Khi `status: Accepted`, Apple cung cấp **notarization ticket**; Gatekeeper có thể tra ticket online hoặc đọc ticket được gắn (*stapled*) vào artifact.

Thứ tự thường dùng:

1. Tạo app bundle và ký đầy đủ những thành phần cần thiết.
2. Tạo `.dmg` hoặc `.pkg` đúng cấu trúc phân phối.
3. Gửi artifact bằng **`xcrun notarytool submit`**.
4. Chờ kết quả và **xác nhận `Accepted`**, không chỉ xác nhận upload thành công.
5. Nếu bị từ chối, tải log và sửa đúng vấn đề signing/hardened runtime/entitlements.
6. Gắn ticket bằng **`xcrun stapler staple`** khi artifact được hỗ trợ.
7. Chạy **`xcrun stapler validate`** và kiểm tra Gatekeeper trên hệ thống mục tiêu.
8. Tạo checksum của artifact **sau khi staple**, rồi publish.

Ví dụ trên một máy Mac đã cấu hình **keychain profile `release-notary`** hợp lệ (tên do người phát hành tạo trước, không phải credential có sẵn mặc định):

~~~bash
xcrun notarytool submit "dist/ExampleDesk-1.0.dmg" --keychain-profile "release-notary" --wait
~~~

Khi thành công cần nhìn thấy kết quả **`status: Accepted`**. Nếu bị `Invalid`, lấy **submission ID thực** trả về để tra log:

~~~bash
xcrun notarytool log SUBMISSION_ID --keychain-profile "release-notary" "notary-log.json"
~~~

`SUBMISSION_ID` trong mảnh lệnh là **mã do `notarytool` trả về**, không phải một giá trị có thể đoán. Hãy thay bằng ID đã nhận. Không in Apple ID password/API private key ra build logs; profile `release-notary` phải được cấu hình trong môi trường bảo vệ secrets.

Sau khi **Accepted**:

~~~bash
xcrun stapler staple "dist/ExampleDesk-1.0.dmg"
xcrun stapler validate "dist/ExampleDesk-1.0.dmg"
~~~

Những lệnh này đòi file thực tồn tại và ticket có thể truy xuất. **`stapler validate` kiểm tra ticket đã được gắn**, không thay thế việc xác minh code signature hay Gatekeeper assessment.

**Không dùng `altool` cho notarization mới.** Apple đã ngừng nhận upload notarization từ `altool` từ **01/11/2023**; `notarytool` hoặc Notary API là hướng hiện hành.

## 7. macOS: các trạng thái nên kiểm tra rõ

| Trạng thái | Ý nghĩa | Có phát hành ngay được không? |
| --- | --- | --- |
| `codesign --verify` thành công | Chữ ký code được kiểm tra trên đối tượng đang chọn | **Chưa đủ** nếu quy trình yêu cầu notarization. |
| `notarytool` upload thành công | Apple đã nhận artifact để kiểm tra | **Chưa**. Phải chờ và xem Accepted/Invalid. |
| `notarytool` trả `Accepted` | Notarization service chấp nhận submission | Tiếp tục staple/verify nếu workflow yêu cầu. |
| `stapler validate` thành công | Ticket notarization phù hợp đã gắn vào artifact | Vẫn nên thử Gatekeeper và chạy trên máy sạch. |
| `spctl --assess` được policy cho phép | Gatekeeper đánh giá đối tượng chấp nhận trong môi trường đó | Cần thêm smoke test chức năng/cài đặt. |
| `notarytool` trả `Invalid` | Artifact bị từ chối | **Không**; đọc log, sửa và submit lại. |

Với app phân phối **qua Mac App Store**, quá trình submission/xét duyệt là workflow riêng và không áp dụng đầy đủ chuỗi Developer ID → notarytool ngoài Store này. Đừng trộn hai bộ chứng thư và giải pháp.

## 8. Linux RPM: chữ ký OpenPGP của package

Đối với hệ sinh thái RPM, công cụ `jpackage --type rpm` tạo một file RPM, nhưng quy trình ký của tổ chức thường thực hiện **sau build** bằng công cụ RPM được cấu hình với khóa OpenPGP.

Ví dụ đóng gói trên Linux phù hợp:

~~~bash
jpackage --type rpm --name exampledesk --app-version 1.0 --input input --main-jar app.jar --dest dist
~~~

Tên file đầu ra phụ thuộc version/release/architecture; tìm **file RPM thực** do lệnh tạo. Giả sử file đó được đặt ở đường dẫn:

~~~text
dist/exampledesk-1.0-1.x86_64.rpm
~~~

Đường dẫn trên là **ví dụ**, không bảo đảm tên gói của mọi bản `jpackage` đều giống nhau.

Khi signing environment đã có OpenPGP private key được bảo vệ và RPM macros đúng:

~~~bash
rpmsign --addsign "dist/exampledesk-1.0-1.x86_64.rpm"
~~~

Để xác minh trên máy có public key của nhà phát hành đã được import vào RPM trust store:

~~~bash
rpmkeys --checksig --verbose "dist/exampledesk-1.0-1.x86_64.rpm"
~~~

**Không chỉ nhìn thấy từ “digest OK”.** Cần biết chữ ký **đúng key** và public key đáng tin cậy theo chính sách của distro/khách hàng. Một kết quả `NOKEY` cho thấy thiếu public key phù hợp trong trust store; không được đánh đồng với bản ký đã được tin cậy.

Quy trình RPM an toàn:

1. Tạo RPM.
2. Ký bằng key phát hành đúng tổ chức.
3. Công bố/distribute **public key** qua kênh đáng tin và ghi fingerprint được kiểm tra.
4. Import key theo quy trình quản trị hệ thống.
5. `rpmkeys --checksig`/test cài đặt từ repo.
6. Nếu dùng repository, kiểm tra thêm metadata repo, TLS, chính sách phân phối và quy tắc xác minh của package manager.

Không đặt private key RPM vào repository hoặc image/container chia sẻ; chỉ key công khai được phân phối cho máy nhận.

## 9. Debian/Ubuntu `.deb`: khác biệt quan trọng với RPM

Với Debian/Ubuntu, mô hình an toàn của **APT repository** dựa trên **chữ ký số của metadata repository**, điển hình là file **`InRelease`**, rồi kiểm tra các hash của `Packages` và `.deb` theo chuỗi tin cậy:

~~~text
Trusted repository signing key
         |
         v
Signed InRelease metadata
         |
         v
Hashes of Packages index
         |
         v
Hashes of .deb files
         |
         v
Downloaded .deb matches trusted repository metadata
~~~

Vì vậy câu “ký từng `.deb` rồi `dpkg -i` tự verify bằng chính sách APT” là **sai**.

Ví dụ build:

~~~bash
jpackage --type deb --name exampledesk --app-version 1.0 --input input --main-jar app.jar --dest dist
~~~

Sau build, bạn có hai con đường phát hành khác nhau:

### 9.1. Phân phối qua APT repository

Đưa file `.deb` vào một repository có metadata được tạo đúng, ký **`InRelease`** bằng key repository và cấu hình client chỉ tin key cụ thể của repo, ví dụ qua **`Signed-By`**/keyring chuyên dụng theo chính sách hiện hành.

Khi client chạy `apt update` và cài package từ repository đã cấu hình, APT xác minh chữ ký metadata và hash theo chuỗi tin cậy. **Chỉ ký file `.deb` theo cách bên ngoài không tạo ra một repository APT đáng tin cậy.**

### 9.2. Phân phối một file `.deb` trực tiếp

Có thể cung cấp **detached OpenPGP signature** và yêu cầu người nhận xác minh thủ công. Ví dụ sau giả định có `exampledesk.deb` và khóa ký phù hợp:

~~~bash
gpg --armor --detach-sign --output exampledesk.deb.asc exampledesk.deb
gpg --verify exampledesk.deb.asc exampledesk.deb
~~~

Trong thực tế, tên file `.deb` phải khớp tên artifact đã tạo. Cần bảo đảm người nhận có **public key đúng** và đã xác minh fingerprint độc lập. **`dpkg -i exampledesk.deb` không tự động kiểm tra detached signature này.**

Đây là lựa chọn khác mô hình APT repository. Với môi trường nhiều máy và cập nhật thường xuyên, một repository có `InRelease` ký đúng và cấu hình `Signed-By` thường có ưu điểm quản trị hơn so với phát hành các file `.deb` rời không có kênh cập nhật xác thực.

**Không dùng `apt-key add` hoặc `trusted=yes` như cách cấu hình mặc định cho repo mới**, cũng không khuyên dùng `--allow-unauthenticated` để vượt cảnh báo chữ ký. Các cách tắt trust check làm mất lợi ích an toàn của hệ thống phân phối.

## 10. Checksum SHA-256: nên dùng nhưng không thay chữ ký

Một digest SHA-256 giúp phát hiện bytes thay đổi khi so với một giá trị đã được xác thực từ kênh đáng tin.

Các lệnh xem hash theo OS:

**Windows PowerShell:**

~~~powershell
Get-FileHash -Algorithm SHA256 -Path "dist\ExampleDesk-1.0.msi"
~~~

**Linux:**

~~~bash
sha256sum "dist/exampledesk-1.0-1.x86_64.rpm"
~~~

**macOS:**

~~~bash
shasum -a 256 "dist/ExampleDesk-1.0.dmg"
~~~

Kết quả là chuỗi hex có **64 ký tự** cho SHA-256, thay đổi theo **bytes của artifact cuối**. Không in một hash “mẫu” rồi coi là đúng cho artifact chưa được tạo.

### Khi nào tính checksum?

- Sau khi kết thúc **mọi bước làm thay đổi artifact**: ký, timestamp, staple notarization, hoặc đóng gói lại.
- Trên máy CI phát hành đáng tin; lưu tên file, version, OS, architecture và hash.
- Khi download, so với manifest được xác thực; nếu hash khác, dừng cài đặt và điều tra.
- Khi kiểm tra nguồn gốc, vẫn cần **chữ ký và trust chain**. Hash không biết ai đã tạo file.

### Ví dụ Java 17 độc lập: SHA-256 không phải chữ ký

Tạo tệp **`Sha256VectorDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class Sha256VectorDemo {
    static String sha256(String text) throws Exception {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        byte[] digest =
                MessageDigest.getInstance("SHA-256").digest(bytes);
        return HexFormat.of().formatHex(digest);
    }

    public static void main(String[] args) throws Exception {
        String expected =
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

        System.out.println(sha256("abc").equals(expected));
        System.out.println(sha256("abcd").equals(expected));
    }
}
~~~

Chạy bằng JDK hiện hành có hỗ trợ Java 17:

~~~bash
javac --release 17 Sha256VectorDemo.java
java Sha256VectorDemo
~~~

**Stdout chính xác:**

~~~text
true
false
~~~

`"abc"` là test vector SHA-256 chuẩn; sửa nội dung thành `"abcd"` làm digest khác. Nhưng ví dụ **không biết ai tạo giá trị `expected`**. Nếu kẻ tấn công thay cả dữ liệu và checksum, một phép so tự thân không xác minh nhà phát hành. Đó là lý do cần thêm **chữ ký và key trust**.

### Ví dụ Java 17: tính SHA-256 file lớn không đọc toàn bộ vào RAM

Tạo tệp **`PackageHash.java`**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class PackageHash {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java PackageHash <artifact>");
            System.exit(2);
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        System.out.println(HexFormat.of().formatHex(digest.digest()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PackageHash.java
java PackageHash path/to/final-package
~~~

Đây là **chương trình chạy được nhưng cần đối số là đường dẫn file thật**. Stdout là **SHA-256 của file đã chọn**, không có một giá trị cố định trước khi biết bytes. Nó chỉ giúp xác nhận integrity khi so với giá trị kỳ vọng từ nguồn được tin cậy, **không tự kiểm tra Authenticode/Apple notarization/GPG signature**.

## 11. Ví dụ Java: chữ ký số kiểm tra được, nhưng chưa có chứng thực OS

Để hiểu khác biệt **signature** và **trusted publisher**, có thể ký một payload nhỏ bằng một cặp RSA key tạo tạm trong bộ nhớ. Ví dụ dưới đây chỉ phục vụ đào tạo cryptography, **không phải cách ký installer production**.

Tệp **`SignatureConceptDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;

public class SignatureConceptDemo {
    static boolean verify(PublicKey key, byte[] data, byte[] sig)
            throws Exception {
        Signature checker = Signature.getInstance("SHA256withRSA");
        checker.initVerify(key);
        checker.update(data);
        return checker.verify(sig);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair pair = generator.generateKeyPair();
        byte[] original = "release".getBytes(StandardCharsets.UTF_8);
        byte[] changed = "releases".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(original);
        byte[] signature = signer.sign();

        System.out.println(verify(pair.getPublic(), original, signature));
        System.out.println(verify(pair.getPublic(), changed, signature));

        KeyPair unrelated = generator.generateKeyPair();
        System.out.println(verify(unrelated.getPublic(), original, signature));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SignatureConceptDemo.java
java SignatureConceptDemo
~~~

**Stdout chính xác trên JDK có thuật toán chuẩn này:**

~~~text
true
false
false
~~~

Ba kết quả lần lượt cho thấy: dữ liệu gốc + đúng public key → xác minh thành công; sửa dữ liệu → thất bại; dùng public key không tương ứng → thất bại.

**Giới hạn cố ý:** ví dụ tự tạo RSA keypair **không có CA chain, Developer ID, Authenticode certificate hoặc repository key trust**. Chữ ký số học hợp lệ **chưa đủ** để Windows/macOS/Linux coi nhà phát hành đáng tin. Với gói thật phải dùng signing tool/certificate/repository policy của nền tảng; **đừng đưa khóa thử nghiệm vào bản phát hành**.

## 12. Lưu ý quan trọng: ký JAR không đồng nghĩa ký native package

`jarsigner` là công cụ Java hỗ trợ ký và xác minh chữ ký của **JAR**:

~~~bash
jarsigner -verify -verbose -certs signed-library.jar
~~~

Lệnh trên là **mảnh thao tác** chỉ có ý nghĩa khi file JAR đã được ký và certificate/trust phù hợp. Chữ ký JAR có thể hữu ích trong một số chuỗi phân phối thư viện, nhưng:

- Nó **không thay thế** Authenticode trên `.exe`/`.msi` của Windows.
- Nó **không thay thế** Apple Code Signing của `.app`/`.pkg` hoặc Apple notarization.
- Nó **không thay thế** chữ ký RPM hoặc APT repository `InRelease`.
- Một file JAR ký hợp lệ có thể vẫn không chạy được nếu module graph, native library hoặc runtime thiếu thành phần.

Đề bài về **ký gói cài đặt** cần kiểm tra **artifact mà OS thực sự tải/cài/chạy**, không dừng ở kiểm tra mỗi JAR nguồn.

## 13. Kiểm thử gói đã ký trên máy sạch

Chữ ký thành công là một checkpoint, chưa phải hoàn thành release. Test end-to-end:

| Câu hỏi | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Artifact đúng OS/arch/version? | EXE/MSI đúng build | DMG/PKG đúng build | RPM/DEB đúng distro/arch |
| Chữ ký hợp lệ? | `signtool verify /pa` | `codesign --verify`; `pkgutil --check-signature` với PKG | `rpmkeys --checksig`; APT `InRelease` |
| Nhà phát hành/key tin cậy? | Certificate chain và publisher đúng | Developer ID/Apple signing identity và policy | RPM key fingerprint/apt Signed-By |
| Notarization? | Không áp dụng | `notarytool Accepted`, `stapler validate`, Gatekeeper | Không áp dụng |
| Timestamp? | Kiểm tra RFC 3161 timestamp | Kiểm tra signing/notary theo Apple policy | Kiểm tra key validity/repository metadata |
| Artifact có bị sửa sau ký? | So chữ ký và SHA-256 của final file | So chữ ký/ticket và SHA-256 sau staple | So chữ ký/hash repo và SHA-256 |
| Cài và chạy? | Cài MSI/EXE, mở launcher | Mount DMG, mở APP hoặc cài PKG | Cài từ trusted repo rồi chạy |
| Nâng cấp/gỡ? | Test upgrade, uninstall | Test update/reinstall, removal | Test package manager upgrade/remove |

Các trường hợp âm tính cũng quan trọng:

- **Tampered artifact:** thay đổi file sau ký thì verify phải thất bại; không bao giờ bỏ qua.
- **Wrong signer:** chữ ký hợp lệ về toán học nhưng identity không đúng nhà phát hành được phê duyệt → fail release.
- **Expired/revoked/unknown certificate:** xử lý theo chính sách OS và timestamp, không tự cho phép.
- **Notarization `Invalid`:** xem log và sửa root cause, không cứ lặp submit.
- **RPM `NOKEY` / APT thiếu trusted repo key:** import/cấu hình key **đúng fingerprint được xác thực**, không tắt cơ chế kiểm tra.
- **Installer chạy nhưng app không khởi động:** kiểm tra runtime, module/native dependency, quyền hệ thống; chữ ký không sửa lỗi chức năng.

**Máy sạch** ở đây là VM/test runner có trust store và policy đại diện cho người dùng mục tiêu, **không phải** máy developer đã import tùy tiện mọi chứng chỉ tự ký.

## 14. CI/CD: quản lý khóa và danh tính phát hành

Một pipeline ký có quyền rất cao: ai nắm được khóa có thể phát hành phần mềm mang danh tính tổ chức. Nên thiết kế các ranh giới:

1. **Build reproducible/provenance:** biết commit, dependency, toolchain, OS, artifact digest trước ký.
2. **Tách build khỏi signing:** runner build ít đặc quyền; signing runner/service có kiểm soát và approvals cần thiết.
3. **Private key trong HSM/KMS/Keychain/secret manager**, không đặt trong repo, source code, CI logs hoặc container image.
4. **Giới hạn quyền và scope:** chỉ nhánh/tag phát hành được yêu cầu ký; có approval, audit, expiration, rotation.
5. **Bảo vệ timestamp và notarization credentials:** không ghi Apple ID app-specific password/API key hoặc PFX password ra console.
6. **Xác minh ngay sau ký:** thất bại ở một bước → chặn publish; không cho phép pipeline chuyển tiếp chỉ vì file đã tồn tại.
7. **Không sửa binary sau khi ký** ngoài các bước được đặc tả như stapling, và xác minh lại sau bước đó.
8. **Tạo manifest final** gồm OS, arch, version, signing identity, SHA-256 final bytes, notary submission ID khi áp dụng, toolchain/JDK.
9. **Kiểm thử tải xuống bằng kênh giống người dùng**, kiểm tra proxy/CDN không làm thay đổi payload.
10. **Có quy trình thu hồi khóa và thu hồi release** khi nghi ngờ compromise; chữ ký không loại bỏ khả năng phát hành sai hoặc bị đánh cắp key.

### Ví dụ release gate dạng giả mã

~~~text
if build_or_tests_failed: BLOCK
if signing_failed: BLOCK
if signer_identity_not_approved: BLOCK
if signature_verification_failed: BLOCK
if macos_outside_store_and_notarization_required:
    if notary_status != Accepted: BLOCK
    if stapled_ticket_required_and_invalid: BLOCK
if platform_install_or_launch_test_failed: BLOCK
calculate_final_sha256()
publish_release_and_audit_evidence()
~~~

Đây là **giả mã**, không phải script có thể thực thi trực tiếp. Trạng thái **PASS** phải dựa trên exit code/tool output/identity được kiểm tra, không chỉ file mang đuôi `.dmg`, `.msi` hoặc `.rpm`.

## 15. Lỗi phổ biến và cách khắc phục

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `jpackage` thành công nên tự cho là đã ký | Packaging và code signing khác nhau | Thêm signing/verification theo OS. |
| Cố dùng `--mac-sign` trên Windows | Cờ chỉ dành macOS | Windows dùng Authenticode/SignTool hoặc dịch vụ ký phù hợp. |
| Dùng SHA-1 làm thuật toán ký mới | Không phù hợp chính sách tin cậy hiện đại | SHA-256 với `/fd`, RFC 3161 `/tr` và `/td`. |
| Ký nhưng không timestamp trên Windows | Chữ ký có thể mất hiệu lực khi chứng thư hết hạn | Dùng timestamp server tin cậy và xác minh timestamp. |
| Dùng self-signed cert để phát hành công khai | Không thuộc chain CA tin cậy mặc định | Chứng thư/dịch vụ ký phát hành hợp lệ. |
| Cho rằng EV cert sẽ tự xóa mọi SmartScreen warning | Reputation vẫn áp dụng | Ký đúng, phân phối hợp lệ, kiểm thử policy/reputation. |
| Trên macOS chỉ `codesign` mà không notarize khi cần | Gatekeeper có thể từ chối | Developer ID + notarization + staple/verify. |
| Dùng `altool` notarization | Workflow đã ngừng tiếp nhận | Dùng `notarytool` hoặc Notary API hiện hành. |
| Chỉ thấy upload notarization thành công | Chưa biết Accepted hay Invalid | `--wait`, kiểm tra status và log. |
| Gắn ticket trước khi có Accepted | Không có ticket hợp lệ | Chờ acceptance rồi staple/validate. |
| Ký app rồi sửa Info.plist/executable | Có thể làm chữ ký sai | Hoàn tất nội dung trước ký, verify lại. |
| Cho rằng `dpkg -i` xác minh chữ ký APT | `dpkg` không thực hiện chuỗi xác thực repo | Dùng APT repository signed InRelease hoặc verify detached signature độc lập. |
| Có chữ ký RPM nhưng `NOKEY` | Chưa có public key tin cậy | Xác minh fingerprint rồi import/configure đúng. |
| Tắt `apt-secure` để cài nhanh | Bỏ bảo vệ chuỗi tin cậy | Sửa repository key/metadata, không bypass. |
| Ký riêng JAR rồi cho rằng MSI/DMG đã được ký | Hai lớp chữ ký khác nhau | Verify đúng OS artifact. |
| Chỉ kiểm tra digest từ cùng nguồn không đáng tin | Kẻ tấn công có thể thay cả file lẫn hash | Xác thực nguồn manifest hoặc chữ ký. |
| Không kiểm thử trên OS/arch mục tiêu | Installer là native, trust policy khác nhau | CI build+verify+install trên từng OS. |

## 16. Checklist phát hành có thể đánh dấu

- [ ] Đã xác định đối tượng phân phối: `app-image`, EXE/MSI, APP/DMG/PKG, RPM hay DEB?
- [ ] Đã build bằng `jpackage` chính thức trên **OS đích**, không dùng API incubating cũ?
- [ ] Đã xác minh ứng dụng chạy được trước ký và dùng đúng JDK/runtime?
- [ ] Có đúng **signing identity** được tổ chức phê duyệt, private key được bảo vệ?
- [ ] Có ký **đúng artifact/những binary cần thiết** và không thay bytes tùy tiện sau ký?
- [ ] Windows: `signtool sign` SHA-256 + RFC 3161 timestamp, `verify /pa`, publisher/chain đúng?
- [ ] macOS: `--mac-sign` Developer ID, `codesign --verify`, notarization `Accepted`, staple và Gatekeeper test khi áp dụng?
- [ ] RPM: chữ ký OpenPGP hợp lệ, key fingerprint đúng và trusted trên máy đích?
- [ ] Debian/Ubuntu: repository `InRelease` được ký, client dùng đúng key `Signed-By` và hash package khớp?
- [ ] Final SHA-256 của artifact được tính **sau toàn bộ signing/stapling** và manifest đi qua kênh bảo vệ?
- [ ] Đã kiểm thử cài đặt, khởi chạy, nâng cấp và gỡ trên máy/VM đại diện cho người dùng?
- [ ] Không có secret/token/private key/Apple password trong repo, log hoặc artifact?
- [ ] Có bằng chứng audit và quy trình phát hành/thu hồi nếu chứng thư hoặc khóa bị lộ?

## 17. Bài tập thực hành

### Bài 1 — Chọn đúng cơ chế Windows

Bạn có `ExampleDesk.msi` đã tạo bằng `jpackage`. Nhóm vận hành nói “chỉ cần đổi tên thành `SignedExampleDesk.msi`”.

**Đáp án:** sai. Tên file không tạo chữ ký. Cần signing identity Authenticode, ký bằng SignTool/dịch vụ phù hợp với `/fd SHA256`, timestamp `/tr ... /td SHA256`, rồi `signtool verify /pa`; cuối cùng kiểm thử MSI trên Windows.

### Bài 2 — Phân biệt notarization và signing

Một `.app` đã qua `codesign --verify` nhưng `notarytool` trả `Invalid`. Có phát hành Developer ID download ngoài Store ngay không?

**Đáp án:** không, nếu quy trình phát hành yêu cầu notarization. Phải đọc notary log, sửa code-signing/hardened runtime/entitlement hoặc cấu trúc bundle, ký lại khi cần, submit lại và xác nhận Accepted.

### Bài 3 — Vì sao checksum đổi sau staple?

Tính SHA-256 trước và sau `xcrun stapler staple` cho cùng một `.dmg`. Giá trị có thể thay đổi vì ticket được gắn vào artifact. **Đáp án:** không dùng hash trước staple làm hash phát hành cuối; tính lại sau khi hoàn tất và verify.

### Bài 4 — DEB và trust

Một người download `exampledesk.deb` qua HTTPS rồi chạy `dpkg -i`. Liệu `dpkg` tự xác minh `InRelease` của APT không?

**Đáp án:** không. Đường `dpkg -i` xử lý file riêng, không thực hiện APT repository authentication. Nếu cần tin cậy chuỗi phân phối, cài qua APT repository có `InRelease` ký đúng hoặc kiểm chứng detached signature/hash theo chính sách độc lập.

### Bài 5 — RPM NOKEY

`rpmkeys --checksig --verbose` hiển thị digest hợp lệ nhưng chữ ký có `NOKEY`. Có đủ điều kiện để công bố “publisher verified” không?

**Đáp án:** không. Cần public key đúng nhà phát hành, xác minh fingerprint qua kênh riêng rồi cấu hình trust trên máy kiểm thử. Hash đúng không tự khẳng định danh tính.

### Bài 6 — Kiểm tra byte tampered bằng Java 17

Chạy:

~~~bash
javac --release 17 Sha256VectorDemo.java
java Sha256VectorDemo
~~~

Kết quả `true`/`false` mô tả điều gì? **Đáp án:** nội dung `"abc"` khớp known SHA-256 vector; `"abcd"` thì không. Chưa có bước ký bởi nhà phát hành.

### Bài 7 — Kiểm chứng toán học của chữ ký

Chạy:

~~~bash
javac --release 17 SignatureConceptDemo.java
java SignatureConceptDemo
~~~

Kết quả `true`, `false`, `false` biểu thị cùng dữ liệu/đúng key thì xác minh được, sửa dữ liệu hoặc dùng key khác thì không. **Đáp án bổ sung:** cần certificate/key trust theo OS mới đủ điều kiện phát hành app tin cậy.

### Bài 8 — Thiết kế release matrix

Lập ba job phát hành độc lập:

- Windows: build MSI → sign Authenticode → verify identity/timestamp → cài/launch.
- macOS: build và ký DMG/PKG → notarytool Accepted → staple/validate → Gatekeeper/launch.
- Linux: RPM ký OpenPGP hoặc DEB trong APT repo có InRelease ký → verify trust → cài/launch.

Điểm nào có thể chia sẻ? **Source tag, dependency policy, version, tests, manifest format và audit gates**. Điểm nào không thể dùng chung? **Công cụ ký, chứng thư, trust policy, format installer và native smoke test**.

## 18. Tài liệu chính thức còn áp dụng

1. [Oracle JDK 25 — `jpackage` command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): `--mac-sign`, `--mac-signing-key-user-name`, loại gói và các tùy chọn theo OS.
2. [Oracle JDK 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): tạo gói bản địa trên OS đích, điều kiện toolchain, ứng dụng và runtime.
3. [Oracle JDK 25 — Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-tool-user-guide.pdf): chương ký app/package trên macOS, Developer ID Application/Installer và option liên quan.
4. [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` trở thành công cụ chính thức từ Java 16.
5. [Microsoft — SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool): ký, timestamp, verify Authenticode; các cờ `/fd`, `/td`, `/pa`.
6. [Microsoft — Time Stamping Authenticode Signatures](https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures): RFC 3161 timestamp và SHA-256, vai trò với thời hạn chứng thư.
7. [Microsoft — SmartScreen Reputation](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation): chữ ký và reputation là tín hiệu khác nhau; EV cert không tự vượt SmartScreen.
8. [Apple — Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution): Developer ID, notarization ticket, Gatekeeper, `notarytool`/`stapler`.
9. [Apple — Customizing notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow): submit/Accepted/log/credentials bằng `notarytool`.
10. [Red Hat Enterprise Linux 10 — Packaging Software with RPM](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/packaging_and_distributing_software/packaging-software-with-rpm): `rpmsign --addsign`, xác minh RPM signature với key đúng.
11. [Debian — Checking Package Authenticity](https://www.debian.org/doc/manuals/debian-handbook/sect.package-authentication.en.html): APT xác thực repository metadata và hash package theo chuỗi tin cậy.
12. [OpenJDK `java.security.Signature` API (Java 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): API ký/verify dữ liệu trong ví dụ Java; không thay chứng thư hệ điều hành.

**Ghi nhớ:** đối với gói tạo bằng `jpackage`, **ký số và xác minh phải đi theo yêu cầu của nền tảng**. Windows dùng Authenticode/SignTool với SHA-256 và timestamp; macOS dùng Apple Code Signing/Developer ID và notarization khi phân phối ngoài Store; RPM dùng OpenPGP signature; Debian/Ubuntu dựa vào APT repository signed metadata hoặc kiểm chứng detached signature riêng. **Ký thành công chưa đủ nếu không kiểm tra identity, trust, policy, final bytes và khả năng cài/chạy trên máy đích.**