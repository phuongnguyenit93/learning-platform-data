# Kiểm tra công cụ đóng gói bản địa tương thích với JDK đang dùng

`jpackage` tạo application image hoặc native installer cho ứng dụng Java. Để tạo được bộ cài, máy build cần có đúng JDK và các công cụ đóng gói mà phiên bản `jpackage` đó sử dụng. Việc một công cụ đã được cài trên máy chưa đủ chứng minh nó tương thích: cần kiểm tra đúng executable, phiên bản, khả năng được tìm thấy qua `PATH` và kết quả đóng gói thử.

Yêu cầu công cụ khác nhau theo hệ điều hành, định dạng đầu ra và phiên bản JDK. Ví dụ, hướng dẫn JDK 16 nêu WiX Toolset cho EXE/MSI trên Windows, `rpm-build` cho RPM trên Red Hat và `fakeroot` cho DEB trên Ubuntu. Các phiên bản JDK mới hơn có thể bổ sung khả năng tương thích với phiên bản toolchain mới. Vì vậy, không nên sao chép nguyên danh sách prerequisite của một JDK sang JDK khác.

Trong module Java 16, `jpackage` là công cụ đã được hoàn thiện và tiếp tục được dùng trong quy trình phát hành Java hiện đại. Bài này hướng dẫn kiểm tra đúng JDK đang chạy, xác minh toolchain Windows/Linux/macOS, nhận diện trường hợp công cụ cũ đã hết hỗ trợ và thực hiện smoke test bằng chính `jpackage` sẽ dùng để phát hành. Nội dung tập trung vào cách kiểm tra còn áp dụng, không khuyến nghị triển khai mới dựa trên toolchain đã legacy.

## 1. Xác định đúng JDK mà lệnh `jpackage` đang sử dụng

Một máy có thể cài nhiều JDK. Lệnh `java`, `javac`, `jlink` và `jpackage` được tìm qua `PATH`; nếu các thư mục JDK khác nhau xuất hiện trước/sau trong `PATH`, chúng có thể không thuộc cùng một bản cài đặt.

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command jpackage -All
where.exe java
where.exe jpackage
java --version
jpackage --version
```

Trên Linux hoặc macOS:

```bash
echo "$JAVA_HOME"
command -v java
command -v jpackage
java --version
jpackage --version
```

Nếu cần bảo đảm đang kiểm tra một JDK cụ thể, gọi trực tiếp executable trong `JAVA_HOME`:

```powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\jpackage.exe" --version
```

```bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/jpackage" --version
```

Kết quả cần xác nhận:

- `java` và `jpackage` thuộc cùng JDK dự định sử dụng.
- Phiên bản hiển thị đúng với phiên bản JDK đã chọn.
- `jpackage` có trên nền tảng build đích và hỗ trợ loại package cần tạo.
- CI runner và máy phát triển đang dùng cùng major JDK hoặc đã có ma trận kiểm thử rõ ràng.

Không chỉ dựa vào `java --version`. Nếu `java` trỏ đến JDK 25 nhưng `jpackage` trỏ đến JDK 16, việc cài toolchain theo tài liệu JDK 25 sẽ không tự làm cho lệnh `jpackage` đang chạy có các khả năng mới.

## 2. Đọc prerequisite theo đúng phiên bản JDK

Trước khi cài thêm công cụ, mở tài liệu `jpackage` tương ứng với JDK đang dùng và kiểm tra:

1. Hệ điều hành và định dạng package có được hỗ trợ không.
2. Công cụ ngoài nào là prerequisite bắt buộc.
3. Tên executable mà `jpackage` tìm trong `PATH`.
4. Phiên bản tối thiểu hoặc major version được hỗ trợ.
5. Tùy chọn nào làm phát sinh thêm prerequisite, ví dụ ký số hoặc tùy chỉnh icon.
6. Thay đổi tương thích trong release notes của JDK.

Có thể lấy danh sách tùy chọn của đúng executable bằng:

```bash
jpackage --help
jpackage --version
```

`--help` cho biết loại package và tùy chọn của JDK hiện tại, nhưng không thay thế phần prerequisite trong tài liệu. Nếu dùng bản phân phối JDK của nhà cung cấp khác, kiểm tra tài liệu của chính bản phân phối đó và thử trên runner sẽ tạo artifact.

## 3. Windows: kiểm tra WiX Toolset

Với JDK 16, tài liệu `jpackage` yêu cầu WiX Toolset cho các định dạng Windows `exe` và `msi`. Công cụ mà JDK 16 tìm kiếm là `candle.exe` và `light.exe`.

Kiểm tra trên PowerShell:

```powershell
Get-Command jpackage -All
Get-Command candle.exe -All
Get-Command light.exe -All
where.exe jpackage
where.exe candle.exe
where.exe light.exe
```

Nếu các lệnh WiX được tìm thấy, kiểm tra phiên bản theo cách mà bản WiX cài đặt hỗ trợ. Với WiX v3, có thể kiểm tra thông tin chương trình bằng:

```powershell
candle.exe -?
light.exe -?
```

Với WiX major mới sử dụng CLI `wix`, kiểm tra:

```powershell
Get-Command wix -All
wix --version
```

Không xem việc có `wix.exe` trong `PATH` là bằng chứng đủ cho JDK 16. JDK 16 được phát hành với tích hợp WiX v3 dựa trên `candle.exe` và `light.exe`; việc dùng CLI của WiX major mới phụ thuộc hỗ trợ được bổ sung trong các JDK về sau.

### Lưu ý vòng đời WiX

Tài liệu JDK 16 ghi yêu cầu WiX 3.0 trở lên. Tuy nhiên, WiX v3 đã hết hỗ trợ cộng đồng từ ngày 6/2/2025. WiX v4 hết hỗ trợ cộng đồng từ ngày 5/2/2025 và WiX v5 hết hỗ trợ cộng đồng từ ngày 5/2/2026. Không nên lấy các phiên bản đã hết hỗ trợ này làm mặc định cho pipeline mới.

JDK 24 bổ sung hỗ trợ WiX v4 và v5 bên cạnh v3, đồng thời có thể tự chọn bản WiX mới nhất trong các phiên bản được hỗ trợ và chuyển đổi custom WiX source từ định dạng v3 sang v4. Điều này không có nghĩa mọi JDK cũ đều có khả năng tương tự. Theo vòng đời hiện tại của WiX, v6 và v7 còn thời gian hỗ trợ cộng đồng, nhưng phải xác minh chính xác JDK đang dùng có hỗ trợ các major đó hay không trước khi chuẩn hóa pipeline.

Nếu một JDK chỉ làm việc với WiX major đã hết hỗ trợ cộng đồng, hãy cân nhắc nâng JDK lên phiên bản có hỗ trợ toolchain còn được duy trì, hoặc dùng quy trình tạo MSI/EXE độc lập được duy trì riêng. Trường hợp phải giữ môi trường cũ vì ràng buộc sản phẩm, cần có hỗ trợ bảo mật mở rộng và kiểm soát rủi ro rõ ràng; không nên cài một toolchain cũ không còn bản vá cho hệ thống build mới.

## 4. Linux: kiểm tra công cụ DEB và RPM

Trên Linux, prerequisite phụ thuộc định dạng package và họ bản phân phối. Hướng dẫn `jpackage` của JDK 16 nêu:

- Với RPM trên Red Hat Linux, cần package `rpm-build`, cung cấp công cụ `rpmbuild`.
- Với DEB trên Ubuntu Linux, cần package `fakeroot`.

Kiểm tra các executable:

```bash
command -v jpackage
jpackage --version
command -v dpkg-deb
dpkg-deb --version
command -v fakeroot
fakeroot --version
command -v rpmbuild
rpmbuild --version
rpm --version
```

Không phải mọi máy Linux đều cần cả bộ công cụ DEB và RPM. Chỉ cài và kiểm tra toolchain tương ứng với loại package mà job sẽ tạo.

### Debian và Ubuntu

`dpkg-deb` thuộc hệ công cụ quản lý gói Debian; `fakeroot` thường cần cho quy trình tạo DEB theo hướng dẫn `jpackage` trên Ubuntu. Trên máy Debian/Ubuntu tối giản, kiểm tra riêng hai lệnh vì việc có `apt` không bảo đảm `fakeroot` đã được cài.

Nếu thiếu `fakeroot` trên Ubuntu, cài bằng package manager của hệ thống theo chính sách máy build:

```bash
sudo apt update
sudo apt install fakeroot
```

Sau cài đặt, xác nhận `command -v fakeroot` và `fakeroot --version`. Không cần chạy lệnh cài đặt trên mọi runner nếu image CI đã cung cấp đúng dependency.

### Fedora, RHEL và các hệ RPM

`rpmbuild` thường được cung cấp bởi package `rpm-build`. Kiểm tra:

```bash
command -v rpmbuild
rpmbuild --version
```

Trên hệ dùng DNF, có thể cài prerequisite bằng:

```bash
sudo dnf install rpm-build
```

Tên package manager hoặc lệnh cài có thể khác theo phiên bản bản phân phối. Trên SUSE hoặc môi trường khác, dùng repository chính thức của hệ thống và kiểm tra lại executable mà `jpackage` cần.

### Phân biệt công cụ tạo package với công cụ cài package

`dpkg-deb` và `rpmbuild` là công cụ tạo gói; `apt`, `dnf` hoặc `zypper` chủ yếu được người dùng dùng để cài và quản lý package. Có `apt` hoặc `dnf` không đồng nghĩa mọi prerequisite đóng gói đã sẵn sàng.

## 5. macOS: kiểm tra công cụ đóng gói và Xcode Command Line Tools

`jpackage` tạo `pkg` hoặc `dmg` trên macOS bằng công cụ native của hệ điều hành. Khi tùy chỉnh quy trình, cần xác nhận các tiện ích đóng gói có sẵn và đúng môi trường:

```bash
command -v jpackage
jpackage --version
command -v pkgbuild
command -v productbuild
command -v hdiutil
pkgbuild --help
productbuild --help
hdiutil help
```

Theo hướng dẫn `jpackage` của JDK 16, Xcode Command Line Tools cần có khi dùng `--mac-sign` để yêu cầu ký package hoặc dùng `--icon` để tùy chỉnh icon của DMG. Kiểm tra vị trí bộ công cụ:

```bash
xcode-select -p
codesign --version
xcrun --find notarytool
xcrun notarytool --help
```

`xcode-select -p` xác nhận đường dẫn developer tools đang được chọn. Nếu tùy chọn ký hoặc tùy chỉnh icon được dùng trong CI, hãy xác minh các công cụ cần thiết có mặt trên runner và đúng phiên bản Xcode/Command Line Tools mà quy trình phát hành yêu cầu.

Ký code và notarization là các bước phát hành riêng cần danh tính nhà phát hành, chứng thư và thông tin xác thực phù hợp. Việc `jpackage` tạo được file DMG/PKG không chứng minh ứng dụng đã được ký, notarize hoặc vượt qua Gatekeeper.

## 6. `app-image` giúp kiểm tra phần nào?

`app-image` là application bundle đã được đóng gói, gồm launcher, ứng dụng và runtime nếu có. Đây là cách tốt để xác minh JAR, main class, resource và runtime image trước khi tạo installer:

```bash
jpackage \
  --type app-image \
  --name ToolCheck \
  --input build/libs \
  --main-jar tool-check.jar \
  --main-class com.example.tools.Main \
  --dest build/package-test \
  --verbose
```

Thay `build/libs`, `tool-check.jar` và tên main class bằng artifact của ứng dụng. Lệnh này kiểm tra khả năng tạo application image trên nền tảng hiện tại. Nó không xác nhận WiX, `fakeroot`, `rpmbuild` hay toàn bộ installer toolchain hoạt động, vì `app-image` không tạo EXE/MSI/DEB/RPM/DMG/PKG.

Sau khi app-image hoạt động, cần chạy thêm một smoke test bằng đúng loại installer sẽ phát hành. Ví dụ trên Linux:

```bash
jpackage \
  --type deb \
  --name ToolCheck \
  --input build/libs \
  --main-jar tool-check.jar \
  --main-class com.example.tools.Main \
  --dest build/package-test \
  --temp build/jpackage-temp \
  --verbose
```

Trên Windows, thay `--type deb` bằng `--type msi` hoặc `exe`; trên macOS, dùng `pkg` hoặc `dmg`. Thư mục `--temp` phải mới hoặc rỗng theo yêu cầu của lệnh; nếu chạy lại, hãy dùng thư mục tạm khác hoặc dọn thư mục build thử nghiệm trước.

## 7. Smoke test theo từng nền tảng

Một kiểm tra đáng tin cậy cần chạy trên cùng loại runner và cùng phiên bản JDK sẽ dùng khi phát hành:

| Nền tảng | Kiểm tra toolchain | Smoke test package |
|---|---|---|
| Windows | `jpackage --version`, `where.exe candle.exe`, `where.exe light.exe`, `wix --version` nếu JDK hỗ trợ CLI đó | Tạo `--type msi` hoặc `--type exe`, sau đó cài thử trên Windows sạch. |
| Debian/Ubuntu | `dpkg-deb --version`, `fakeroot --version` | Tạo `--type deb`, cài thử trên bản phân phối mục tiêu. |
| Fedora/RHEL | `rpmbuild --version`, `rpm --version` | Tạo `--type rpm`, cài thử trên bản phân phối mục tiêu. |
| macOS | `pkgbuild`, `productbuild`, `hdiutil`; kiểm tra Xcode tools nếu ký hoặc tùy chỉnh icon | Tạo `--type pkg` hoặc `--type dmg`, mở/cài thử trên macOS mục tiêu. |

Sau khi tạo thành công, kiểm tra launcher, runtime, resource, icon, metadata, chữ ký, nâng cấp và gỡ cài đặt. Không kết luận tương thích chỉ dựa vào việc lệnh `--version` chạy được.

## 8. Dùng `--verbose` và thư mục tạm để tìm lỗi

Khi `jpackage` báo lỗi, chạy lại với `--verbose` để lấy thêm thông tin. Nếu cần giữ file trung gian, chỉ định `--temp` tới một thư mục mới hoặc rỗng:

```bash
jpackage \
  --type app-image \
  --name ToolCheck \
  --input build/libs \
  --main-jar tool-check.jar \
  --main-class com.example.tools.Main \
  --dest build/package-test \
  --temp build/jpackage-debug \
  --verbose
```

Đọc thông báo để phân biệt các nhóm lỗi:

- **Không tìm thấy công cụ:** executable chưa cài, không có trong `PATH` hoặc shell/runner đang dùng PATH khác.
- **Sai phiên bản hoặc CLI:** JDK gọi công cụ bằng tên/tham số mà major version đang cài không cung cấp.
- **Sai quyền:** runner không có quyền ghi thư mục tạm, thư mục đầu ra hoặc thực hiện bước cần quyền quản trị.
- **Sai định dạng package:** chọn loại package không được hỗ trợ trên hệ điều hành hiện tại.
- **Lỗi ứng dụng:** thiếu JAR, main class, resource hoặc module runtime; đây không nhất thiết là lỗi toolchain native.
- **Lỗi ký số:** thiếu certificate, identity, entitlement hoặc cấu hình notarization; package có thể đã được tạo nhưng chưa đủ điều kiện phát hành.

Nếu nhiều phiên bản toolchain cùng tồn tại, kiểm tra executable mà tiến trình thực sự gọi. Đừng chỉ kiểm tra danh sách chương trình đã cài; `PATH` có thể ưu tiên một phiên bản khác.

## 9. Khóa phiên bản toolchain trong CI

Để build có thể tái tạo, mỗi job CI nên ghi nhận:

- Nhà cung cấp, phiên bản và đường dẫn JDK.
- Kết quả `java --version`, `jpackage --version` và `jlink --version`.
- Hệ điều hành, phiên bản runner và kiến trúc CPU.
- Phiên bản WiX, `fakeroot`, `rpmbuild`, Xcode Command Line Tools hoặc tiện ích native có liên quan.
- Loại package được tạo và toàn bộ lệnh `jpackage`.
- Log `--verbose`, checksum artifact và kết quả smoke test.

Ví dụ bước chẩn đoán đầu job Linux:

```bash
echo "JAVA_HOME=$JAVA_HOME"
command -v java
command -v jpackage
java --version
jpackage --version
jlink --version
command -v fakeroot && fakeroot --version
command -v rpmbuild && rpmbuild --version
```

Trong script CI, nếu một tool là prerequisite của job, hãy để job thất bại sớm khi tool thiếu thay vì bỏ qua lỗi bằng cách biến mọi lệnh kiểm tra thành tùy chọn. Job DEB cần kiểm tra tool DEB; job RPM cần kiểm tra tool RPM; job macOS ký package cần kiểm tra Xcode tools và cấu hình ký số.

Không cập nhật toolchain lên major mới trong cùng lần thay đổi với logic đóng gói mà không có kiểm thử riêng. Khi nâng JDK hoặc WiX, tạo một nhánh kiểm tra tương thích, tạo artifact thật và cài thử trước khi đổi cấu hình phát hành chính.

## 10. Ma trận quyết định khi công cụ không tương thích

| Tình huống | Cách xử lý phù hợp |
|---|---|
| JDK không tìm thấy công cụ dù đã cài | Kiểm tra `PATH`, `JAVA_HOME` và executable thực tế; mở lại runner/shell nếu môi trường vừa thay đổi. |
| Công cụ có mặt nhưng CLI không đúng major mà JDK gọi | Đối chiếu release notes của JDK; chọn tổ hợp đã được xác nhận hoặc nâng JDK. |
| JDK 16 yêu cầu WiX v3 nhưng chính sách mới không cho dùng WiX hết hỗ trợ | Không đưa WiX v3 không còn bản vá vào pipeline mới; cân nhắc nâng JDK hoặc dùng quy trình installer được duy trì độc lập. |
| JDK mới có hỗ trợ WiX major mới nhưng custom WiX source không tương thích | Dùng định dạng source được JDK hỗ trợ hoặc chuyển đổi theo tài liệu; chạy smoke test lại. |
| Thiếu `fakeroot` khi tạo DEB | Cài package `fakeroot` từ repository của bản phân phối và kiểm tra lại. |
| Thiếu `rpmbuild` khi tạo RPM | Cài package `rpm-build` hoặc package tương ứng trên hệ RPM và kiểm tra lại. |
| `app-image` thành công nhưng installer thất bại | Kiểm tra prerequisite riêng của installer; app-image không kiểm tra toolchain tạo package. |
| Package tạo được nhưng ký/notarize thất bại | Kiểm tra certificate, identity, entitlement, tài khoản và toolchain bảo mật của nền tảng. |

Nếu không thể dùng tổ hợp JDK và công cụ được duy trì, tách bước tạo native installer sang một công cụ đóng gói khác có vòng đời hỗ trợ phù hợp. JAR hoặc application image có thể là đầu vào cho quy trình đó, nhưng phải kiểm thử lại launcher, runtime, metadata, nâng cấp và gỡ cài đặt.

## 11. Checklist trước khi đưa toolchain vào production

- Đã xác nhận đúng JDK và đúng `jpackage` mà CI sẽ gọi.
- Đã đọc prerequisite và release notes của đúng JDK, không sao chép từ phiên bản khác.
- Mọi executable bắt buộc đều có trong `PATH` của runner và đúng phiên bản.
- WiX đang dùng còn được hỗ trợ và được JDK hiện tại xác nhận tương thích.
- Công cụ DEB/RPM đã được kiểm tra trên đúng họ Linux.
- Công cụ macOS và Xcode Command Line Tools đã sẵn sàng nếu dùng ký số hoặc tùy chỉnh icon.
- `app-image` đã tạo và chạy được.
- Native installer thật đã được tạo bằng `--type` dự kiến.
- Package đã được cài, khởi chạy, nâng cấp và gỡ cài đặt thử trên nền tảng đích.
- Log, phiên bản công cụ và artifact được lưu để có thể tái tạo lần build.

## 12. Cách áp dụng trong quy trình Java hiện đại

- Xem phiên bản JDK là một phần của toolchain, không chỉ là phiên bản dùng để chạy ứng dụng.
- Kiểm tra executable và version thay vì chỉ dựa vào trạng thái cài đặt trên máy.
- Phân biệt prerequisite cho `app-image` với prerequisite của installer cụ thể.
- Dùng tài liệu của đúng JDK để xác định WiX, `fakeroot`, `rpm-build` và Xcode tools.
- Theo dõi vòng đời hỗ trợ của công cụ ngoài; tránh dùng major đã hết bản vá cho pipeline mới.
- Chạy smoke test bằng chính loại package cần phát hành trên runner đích.
- Ghi lại JDK, toolchain, OS, kiến trúc và log để tái tạo artifact.

Kiểm tra công cụ đóng gói cần xác nhận cả ba yếu tố: đúng phiên bản JDK, đúng executable mà JDK gọi và khả năng tạo/cài package thực tế. Danh sách prerequisite trong tài liệu là điểm bắt đầu; smoke test trên runner đích mới xác nhận tổ hợp đang dùng hoạt động. Cách làm này giúp giữ quy trình `jpackage` ổn định và tránh phụ thuộc vào công cụ đã hết hỗ trợ.

## Tài liệu tham khảo

- [Oracle JDK 16 — Packaging Overview](https://docs.oracle.com/en/java/javase/16/jpackage/packaging-overview.html)
- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle JDK 24 Release Notes — jpackage supports WiX Toolset v4 and v5](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html)
- [FireGiant — WiX Toolset lifecycle and supported versions](https://docs.firegiant.com/wix/)
