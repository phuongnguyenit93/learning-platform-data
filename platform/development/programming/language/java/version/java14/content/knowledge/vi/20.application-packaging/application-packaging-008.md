# Lập kế hoạch cập nhật runtime và phiên bản ứng dụng khi đóng gói Java với jpackage

## 1. Bài toán: ứng dụng và Java runtime có vòng đời cập nhật riêng

Công cụ **jpackage** cho phép tạo application image hoặc bộ cài native từ ứng dụng Java. Một gói self-contained thường chứa **launcher, JAR/module của ứng dụng, cấu hình launcher và Java runtime được đóng cùng gói**. Người dùng không phải tự cài JDK riêng, nhưng đổi lại **đơn vị phát hành ứng dụng phải chịu trách nhiệm cập nhật cả runtime nhúng**.

Ví dụ một bản desktop phát hành có thể gồm:

- **Application version:** `2.4.0`, được khai báo trong mã sản phẩm và trong metadata `jpackage --app-version 2.4.0`.
- **Runtime version:** `24.0.2`, ví dụ đúng với môi trường Windows dùng JDK 24.0.2 đã kiểm thử ở bài này.
- **Compile target:** `javac --release 17`; classfile/API Java được kiểm tra tương thích với mức Java 17.
- **Artifact/platform:** image Windows x64, có tên gói và danh tính sản phẩm nhất quán giữa các đợt nâng cấp.

**Ba phiên bản không phải một:** `--app-version` không tự nâng runtime; thay runtime không tự sửa chuỗi version hard-code trong mã; `--release 17` không buộc `jpackage` phải nhúng Java 17. Một lớp đã compile target 17 có thể chạy trên Java runtime mới hơn khi tương thích, nhưng cần kiểm thử.

**Nguyên tắc chính:** với gói có runtime nhúng, khi một bản vá JDK được phê duyệt, hãy **tạo lại runtime/application image và phát hành gói mới**, kiểm tra native installer nhận diện đúng bản update, ký gói và test migration. Chỉ cập nhật Java toàn hệ thống của người dùng **không tự vá thư mục runtime đã nằm bên trong gói jpackage**.

### 1.1. Liên hệ Java 14 mà không dùng kiến thức lỗi thời

`jpackage` xuất hiện **incubating trong Java 14** (JEP 343), tiếp tục incubating ở Java 15 và **trở thành production-ready từ Java 16** (JEP 392). Module hiện hành là **`jdk.jpackage`**, không phải `jdk.incubator.jpackage`.

Tính năng này **vẫn có trong JDK hiện đại**. Bài học chỉ dùng `jpackage`, `jlink` và Java API ổn định, với ví dụ Java 17+, không cần cờ incubating hay preview. Một dự án thực tế nên chọn JDK vendor/release có chính sách hỗ trợ và cập nhật bảo mật phù hợp thay vì cố giữ runtime Java 14 lịch sử.

### 1.2. Mục tiêu học tập

Sau bài, bạn có thể xây dựng quy trình nâng cấp ứng dụng Java đóng gói, phân biệt application version, embedded runtime, compile target và installer revision; sử dụng `--app-version`/`--runtime-image`; kiểm chứng runtime trong image; lựa chọn đường phân phối updates theo OS; quản lý chữ ký, dữ liệu người dùng, migration, rollback và kiểm thử bảo mật.

## 2. Phân loại các thông tin phiên bản

| Thông tin | Ví dụ | Nguồn đáng tin | Cần đổi khi nào? |
| --- | --- | --- | --- |
| Ứng dụng | `2.4.0`, `2.4.1` | Release configuration, build metadata, `--app-version` | Khi phát hành build mới, kể cả bản chỉ vá runtime |
| Runtime nhúng | `24.0.2` | JDK build/vendor dùng tạo image; `runtime/release` | Khi nâng JDK patch/feature theo lịch |
| Compile target | `17` | `javac --release 17` hoặc cấu hình build | Khi đổi API/language baseline |
| Native installer identity | Product/upgrade ID, bundle ID, package name | Configuration của từng nền tảng | Thường giữ ổn định giữa các bản update của cùng sản phẩm |
| Native installer revision | Version/release metadata | Windows/macOS/Linux packaging | Theo yêu cầu nhận diện và so sánh phiên bản của OS |
| Data schema | `5` → `6` | Ứng dụng lưu trong user data | Khi thay cấu trúc dữ liệu cần migration |
| Build provenance | commit/build ID/hash | CI và artifact registry | Mỗi artifact được tạo/ký |

**Không trộn version semantics.** Phiên bản kiểu `MAJOR.MINOR.PATCH` là convention sản phẩm, không phải logic `jpackage` tự áp dụng. Windows installer, macOS package và Debian/RPM có các quy tắc version khác nhau; cần kiểm tra giới hạn định dạng trên từng hệ điều hành. Có thể giữ product version đọc được và một native revision tách biệt khi OS yêu cầu.

**Thông tin Java đầy đủ quan trọng hơn feature number.** `Runtime.version().feature()` chỉ cho biết `24`, chưa biết bản vá `24.0.2`, vendor hoặc build. Release manifest phải ghi **full runtime version, vendor, architecture** và artifact digest để truy tìm thiết bị còn bản runtime có lỗ hổng.

## 3. jpackage tạo runtime và application image ra sao?

### 3.1. Runtime nhúng

Nếu không có `--runtime-image`, `jpackage` dùng `jlink` để tạo runtime từ JDK/toolchain và cấu hình module. Với một ứng dụng Java class-path hoặc modular, kết quả là image có thể chạy bằng launcher native.

Bố cục **Windows minh họa**:

```text
VersionedDesktop/
  VersionedDesktop.exe
  app/
    VersionedDesktop.cfg
    versioned.jar
  runtime/
    bin/
    conf/
    lib/
    release
    ...
```

Vị trí cụ thể có thể khác theo OS/JDK; một số tệp là **chi tiết triển khai**, không phải public contract ổn định. macOS dùng bundle application; Linux có bố cục riêng cho launcher và runtime.

Vì application image chứa Java runtime **riêng**, việc cập nhật `java` trên `PATH` của hệ thống không có nghĩa runtime của gói sẽ thay đổi. Ngược lại, đổi JDK trên runner CI có thể thay đổi runtime **của gói tạo mới**, ngay cả khi code Java và `--app-version` giữ nguyên.

### 3.2. Runtime tự tạo bằng jlink

Nếu cần kiểm soát module hoặc bản Java cụ thể, tạo runtime image trước:

```powershell
jlink --add-modules java.base --strip-debug --no-man-pages --no-header-files --output custom-runtime
```

Sau đó truyền vào `jpackage` bằng `--runtime-image custom-runtime`. Đoạn trên chỉ đủ cho **ví dụ console rất nhỏ** dùng Java base. Ứng dụng thực tế có thể cần `java.desktop`, `java.logging`, `java.net.http`, `java.sql`, `jdk.jfr`, cryptography/service provider, charset, native libraries, JavaFX hoặc những module riêng của app.

**Không giảm module mù quáng** chỉ để gói nhỏ hơn; những đường code hiếm dùng (TLS, fonts, locale, JNI, ServiceLoader, tính năng export) cũng phải được kiểm thử trên runtime image thật.

### 3.3. Thay đổi runtime image trong JDK mới cần regression test

Theo hướng dẫn **Oracle Packaging Overview của JDK 26**, từ **JDK 25 trở lên**, runtime image mà `jpackage` tự tạo **không mặc định bao gồm service bindings** như một số bản trước. Khi ứng dụng phụ thuộc vào service provider modules, cần kiểm tra module set và có thể dùng tùy chọn `--jlink-options` với `--bind-services` theo đúng hướng dẫn của phiên bản JDK được dùng.

**Đây là ví dụ tại sao “chỉ nâng công cụ jpackage” vẫn là một thay đổi sản phẩm:** JDK toolchain có thể làm runtime được nhúng khác trước. Bài test phải bao gồm `ServiceLoader`, các provider bảo mật, TLS, định dạng/locale và chức năng thực tế, thay vì chỉ xác nhận app khởi động.

### 3.4. App image chưa phải native installer

`--type app-image` chỉ tạo thư mục/bundle có thể chạy, phù hợp **smoke test trước khi tạo MSI/EXE/PKG/DEB/RPM**. Với Windows, các loại đóng gói thường là `exe` hoặc `msi`; macOS dùng `dmg` hoặc `pkg`; Linux dùng `deb` hoặc `rpm`.

Theo Oracle, **native package phải được xây dựng trên chính OS đích**, không có một lệnh `jpackage` duy nhất trên Windows để sinh bộ cài Linux/macOS. Thiết lập runner/CI và kiểm thử riêng theo **OS + CPU architecture**.

## 4. Ví dụ thực thi: phiên bản app khác phiên bản runtime

**Tệp `VersionedDesktop.java` — Java 17+:**

```java
public class VersionedDesktop {
    public static void main(String[] args) {
        System.out.println("appRelease=2.4.0");
        System.out.println("runtimeFeature=" + Runtime.version().feature());
    }
}
```

Lệnh PowerShell tại thư mục chứa file; yêu cầu JDK có `javac`, `jar`, `jpackage`:

```powershell
New-Item -ItemType Directory -Force -Path classes,input,dist | Out-Null
javac --release 17 -encoding UTF-8 -d classes VersionedDesktop.java
jar --create --file input/versioned.jar --main-class VersionedDesktop -C classes .
java -jar input/versioned.jar
```

**Bắt buộc xác nhận `javac` và `jar` thành công** trước khi đóng gói; JAR trống hoặc thiếu main class không phải bài test hợp lệ. `java -jar` ở bước này chạy bằng Java trên máy build, chưa kiểm chứng Java runtime nào được nhúng.

Tạo app-image Windows và chạy launcher đã package:

```powershell
jpackage --type app-image --name VersionedDesktop --input input --main-jar versioned.jar --main-class VersionedDesktop --app-version 2.4.0 --win-console --dest dist
& ".\dist\VersionedDesktop\VersionedDesktop.exe"
```

**Stdout đã kiểm chứng trên Windows với JDK 24.0.2:**

```text
appRelease=2.4.0
runtimeFeature=24
```

`--win-console` chỉ dùng cho launcher console trên Windows, không phải flag chung cho macOS/Linux. Nếu JDK dùng đóng gói có feature khác 24, giá trị `runtimeFeature` sẽ khác. Đây là số đo **runtime đang chạy bên trong gói**, không phải số được `jpackage` tự chép từ `--app-version`.

Kiểm tra runtime đầy đủ ngay trong image:

```powershell
Get-Content ".\dist\VersionedDesktop\runtime\release" | Select-String "^JAVA_VERSION="
```

**Kết quả tại môi trường đã thử:**

```text
JAVA_VERSION="24.0.2"
```

Ứng dụng thật nên ghi thêm vendor/build và package checksum trong manifest CI. Không dựa vào output `java -version` của `PATH` để xác định runtime được người dùng chạy bằng launcher app-image.

### 4.1. Kiểm tra `--runtime-image` và nâng app metadata

Sau khi đã có `input/versioned.jar`, có thể tạo runtime đơn giản và package lại với metadata khác:

```powershell
jlink --add-modules java.base --strip-debug --no-man-pages --no-header-files --output custom-runtime
New-Item -ItemType Directory -Force -Path dist-custom | Out-Null
jpackage --type app-image --name VersionedDesktop --input input --main-jar versioned.jar --main-class VersionedDesktop --app-version 2.4.1 --win-console --runtime-image custom-runtime --dest dist-custom
& ".\dist-custom\VersionedDesktop\VersionedDesktop.exe"
```

**Kết quả đã thử trên cùng JDK 24.0.2:**

```text
appRelease=2.4.0
runtimeFeature=24
```

Vì sao `--app-version 2.4.1` mà Java vẫn in `2.4.0`? Vì `appRelease` **được hard-code trong file Java đã biên dịch**, còn `2.4.1` là **metadata app-image**. `jpackage` **không biên dịch lại JAR hay thay nội dung string trong mã**. Runtime vẫn là `24.0.2` vì custom-runtime được tạo bằng cùng JDK. Phép thử cũng quan sát version metadata `2.4.1` trong cấu hình launcher do tool tạo, nhưng vị trí/file cấu hình đó là **implementation detail** có thể đổi theo bản JDK.

**Bài học:** release pipeline phải dùng **một nguồn app version chính thức** để sinh build metadata/UI/About và truyền vào `jpackage --app-version`. Không có ý nghĩa khi UI hiển thị `2.4.0` nhưng installer báo `2.4.1` nếu không giải thích đó là hai khái niệm khác nhau.

### 4.2. Vì sao demo không phải quy trình production hoàn chỉnh?

Hai image trên là **test local trên Windows**, không phải bản cài native được ký hay một hệ thống update. Ứng dụng thật còn phải tạo installer OS-specific, kiểm tra phiên bản theo chính sách installer, ký artifact, thử nâng cấp từ bản cũ, bảo toàn user data và có rollback/monitoring. Ví dụ `java.base` cũng không đáp ứng được ứng dụng thật cần desktop/TLS/JDBC/JavaFX/JFR.

## 5. Xây chính sách cập nhật Java runtime nhúng

### 5.1. Theo dõi bản vá của nhà cung cấp JDK

Runtime nhúng có vòng đời riêng. Cần:

1. Chọn **JDK vendor và dòng phát hành đang được hỗ trợ** theo mục tiêu sản phẩm, license và thời hạn hỗ trợ.
2. Theo dõi lịch update và security advisories/CVEs; lưu feature/update/patch/build chính xác, không chỉ phiên bản major.
3. Đánh giá phạm vi tác động: module nào thực sự có trong runtime image, workload nào có thể chạm lỗ hổng, mức độ khẩn cấp và biện pháp giảm thiểu tạm thời.
4. Tải JDK build đã duyệt từ nguồn xác thực, kiểm tra checksum/chữ ký.
5. Rebuild runtime (mặc định do `jpackage` tạo hoặc riêng qua `jlink`), rồi build lại app-image/native installer.
6. Chạy regression tests, ký bản mới, phát hành theo kênh có kiểm soát.
7. Xác định thiết bị nào đã nhận build mới, thiết bị nào vẫn chạy runtime lỗi, và có chính sách xử lý thiết bị lâu ngày offline.

Đừng mặc định bản feature Java mới nhất là lựa chọn phù hợp duy nhất: nhiều sản phẩm chọn một dòng được vendor hỗ trợ lâu dài và nâng các patch phù hợp, sau đó thử chuyển feature release ở giai đoạn riêng. Khi version không còn được bảo trì, phải có kế hoạch chuyển sang dòng được hỗ trợ.

### 5.2. Phân biệt lịch update thường kỳ và hotfix

- **Bản vá định kỳ:** đưa vào release train theo lịch kiểm thử và khung phân phối đã định.
- **Vấn đề bảo mật khẩn:** rút ngắn vòng đánh giá, chuẩn bị build được ký và kế hoạch rollout/rollback, không bỏ qua xác minh.
- **Nâng feature release JDK:** cần kiểm tra sâu API, GC/JIT, TLS/provider, modules, native libraries, font/locale/timezone, `ServiceLoader`.
- **Bản phát hành chỉ đổi runtime:** dù mã Java không đổi, vẫn là một artifact mới; thường nên tăng **package version/revision** để installer và support nhận diện.

Không lấy **một** lịch cố định áp cho mọi tổ chức. Dựa trên tốc độ sửa lỗi của vendor, yêu cầu pháp lý/bảo mật, thiết bị offline và thời gian đội vận hành có thể phân phối gói.

### 5.3. Ví dụ ma trận phát hành

| Bản sản phẩm | Runtime trong gói | Loại thay đổi | Test bắt buộc |
| --- | --- | --- | --- |
| `2.4.0` | `24.0.2` (demo) | Đường cơ sở | Cài mới, kiểm tra runtime/version |
| `2.4.1` | Bản JDK update đã phê duyệt | Chỉ thay runtime/vá bảo mật | Full regression, installer upgrade, ký lại |
| `2.5.0` | Bản JDK được support và kiểm thử | Tính năng + runtime | Migration, backend compatibility, rollback |

Các dòng là **mô hình minh họa**, không khẳng định các số ví dụ là release JDK hiện tại hoặc khuyến nghị dùng Java 24 dài hạn. Khi phát hành thật, ghi runtime build/vendor đầy đủ trong manifest.

## 6. Native installer: phải giữ danh tính sản phẩm khi nâng bản

### 6.1. Windows: version và upgrade identity

`jpackage` hiện đại hỗ trợ `--app-version`, `--win-upgrade-uuid`, `--win-update-url` và lựa chọn `--win-per-user-install`/`--install-dir`. Khi tạo bản cập nhật:

- **Giữ một upgrade identity ổn định** cho cùng sản phẩm; `--win-upgrade-uuid` là UUID liên kết các bản upgrade. Không tạo UUID mới ngẫu nhiên trong mỗi lần CI build.
- **Tăng phiên bản gói** theo format và quy tắc so sánh của Windows installer. Kiểm tra trên môi trường thật; `2.4.1` trong app-image chưa chứng minh native MSI xử lý mọi version format như mong muốn.
- Giữ nhất quán install scope (per-user/per-machine), tên package, vendor, shortcut/service và đường dẫn trừ khi có migration riêng.
- Kiểm tra app đang mở, quyền cài đặt, tệp bị khóa, thiếu dung lượng, uninstall/replace và trường hợp update thất bại.
- Ký gói và verify sau khi tạo artifact cuối.

**Cần lưu ý:** `--win-update-url` được tài liệu mô tả là **URL nơi có thông tin bản cập nhật**, **không** phải một auto-updater thực hiện đủ việc check, download, verify, install và rollback.

Ví dụ CI **minh họa**, cần biến `$appVersion` và `$stableUpgradeUuid` lấy từ cấu hình phát hành đã thiết lập:

```powershell
jpackage --type msi --name VersionedDesktop --app-version $appVersion --win-upgrade-uuid $stableUpgradeUuid --input input --main-jar versioned.jar --main-class VersionedDesktop --dest installers
```

Lệnh này đòi hỏi **Windows runner, bộ công cụ installer tương ứng và các biến đã được cấp**. Nó không phải đoạn có thể copy chạy ngay nếu chưa có cấu hình build. Một UUID nên được **tạo một lần** khi khởi tạo sản phẩm, lưu trong nơi quản lý cấu hình, và dùng lại cho các bản cập nhật liên tiếp.

### 6.2. macOS: bundle identifier, signing, notarization

Giữ ổn định `--mac-package-identifier` của cùng ứng dụng. Xác định version metadata, signing identity, entitlement, kiến trúc CPU và yêu cầu notarization/Gatekeeper theo kênh phân phối. `jpackage` có `--mac-sign`, nhưng quyền ký và quy trình notarize còn phụ thuộc vào Apple tooling/account.

**Không chỉnh sửa runtime trong một bundle đã ký** rồi nghĩ chữ ký vẫn hợp lệ. Thay đổi nội dung cần tạo/kiểm tra chữ ký phù hợp và kiểm thử install/upgrade trên macOS thật.

### 6.3. Linux: package name, release và repository

Với `deb` và `rpm`, giữ ổn định package identity (ví dụ `--linux-package-name`), dùng version/revision đúng semantics của package manager và kiểm tra quyền/quá trình nâng gói. `--linux-app-release` dùng làm RPM release hoặc Debian revision tùy định dạng.

Nếu ứng dụng phát qua repo, cần quản lý signed repository, dependency, pinning, staged deployment và downgrade policy. Không khẳng định gói build ở một distro sẽ tương thích với mọi distro khác.

### 6.4. Build matrix cho OS và kiến trúc

| Hệ thống | Hình thức phân phối thường gặp | Runner/test cần thiết |
| --- | --- | --- |
| Windows | `app-image`, `exe`, `msi` | Windows + toolchain native, test x64/ARM theo sản phẩm |
| macOS | app bundle, `dmg`, `pkg` | macOS + ký/notarize theo policy |
| Linux | `app-image`, `deb`, `rpm` | Distro/architecture được hỗ trợ + native packaging tools |

`jpackage` **không hỗ trợ cross-platform native packaging**. Build và kiểm thử installer trên OS mục tiêu, không chỉ trên runner CI duy nhất. Trước khi build native package có thể dùng `--type app-image` để chạy smoke test ở đúng môi trường.

## 7. jpackage không tự cung cấp hệ thống auto-update hoàn chỉnh

Đóng gói và **phân phối cập nhật** là hai lớp kiến trúc khác nhau. `jpackage` tạo application image/bộ cài; ứng dụng/đội vận hành phải xác định **ai kiểm tra cập nhật, tải từ đâu, xác minh bằng gì, cài khi nào và quay lui như thế nào**.

Có thể chọn:

1. **Manual update:** người dùng chủ động tải và cài gói đã ký từ nguồn tin cậy.
2. **MDM/enterprise deployment:** bộ phận IT đẩy artifact qua hệ thống quản trị thiết bị, giám sát tuân thủ.
3. **OS package manager:** dùng repo/metadata ký phù hợp trên Linux hoặc hệ thống cập nhật native tương ứng.
4. **Updater riêng:** một tiến trình/công cụ được kiểm soát nhận release manifest, xác minh chữ ký và platform, tải artifact, đóng app, cài gói, xác minh thành công hoặc rollback.

Nếu làm updater riêng, cần chống **downgrade/replay**, giới hạn kích thước, xác minh chữ ký manifest và artifact, phân quyền nâng cấp, xử lý mất mạng, network proxy, lock files và không cài bản sai kiến trúc.

**Chỉ kiểm tra SHA-256 so với hash được tải từ cùng một endpoint không xác thực là chưa đủ.** Kẻ tấn công có thể thay cả gói và chuỗi hash. Phải thiết kế chuỗi tin cậy từ khóa ký/trust anchor tới metadata và gói cuối cùng.

## 8. Migration dữ liệu và rollback an toàn

### 8.1. Tách dữ liệu người dùng khỏi thư mục cài

Thư mục application image là **immutable deployment** trong ý nghĩa vận hành: nâng cấp có thể thay thế nội dung cũ. Không nên lưu settings, dữ liệu người dùng, database hoặc nhật ký cần giữ lâu dài bên trong thư mục JAR/runtime.

Dùng vị trí dữ liệu theo nền tảng:

- Windows: user-data phù hợp dưới `AppData` hoặc nơi quản trị máy với quyền phù hợp.
- macOS: `Application Support` và vùng dữ liệu người dùng tương ứng.
- Linux: quy ước XDG như `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, hoặc user-data directory theo product policy.

Dữ liệu user khác nhau về loại và quyền; không tự khẳng định uninstall luôn giữ chúng. Cần có **chính sách và test** cho uninstall/reinstall.

### 8.2. Có schema version riêng

Một app update có thể đồng thời nâng version Java và thay cấu trúc dữ liệu. Hãy:

- Lưu **data schema version**, không dùng app version để giả định schema.
- Xác định đường nâng từ N-1, N-2 và các bản cũ còn được hỗ trợ.
- Backup/snapshot trước migration không thể đảo ngược.
- Thiết kế migration có transaction hoặc idempotent/checkpoint, xử lý tắt máy bất ngờ.
- Kiểm tra dữ liệu thực trong điều kiện quyền hạn, encryption key và dung lượng ổ đĩa.
- Thử **rollback binary và restore data**; nếu schema mới không thể đọc bằng app cũ, không hứa rằng chỉ downgrade installer sẽ sửa được.

### 8.3. Tương thích giữa desktop client và server

Nếu ứng dụng gọi backend API, cần quy định **khoảng phiên bản client còn được hỗ trợ**, thời hạn chuyển đổi, feature flags, cơ chế báo yêu cầu nâng bản và tương thích giao thức. Một runtime patch không thay hợp đồng API, nhưng phiên bản application mới có thể thay auth, TLS behavior hoặc format dữ liệu, nên vẫn phải test end-to-end.

Không xem app version do client khai báo là bằng chứng xác thực hoặc quyền truy cập.

## 9. CI/CD có khả năng kiểm toán

### 9.1. Luồng phát hành khuyến nghị

```text
Commit/release tag + appVersion + supported JDK vendor/build
                          |
                          v
          Compile with explicit --release target
                          |
                          v
               Unit/integration/security tests
                          |
                          v
                JAR/modules + dependency SBOM
                          |
                          v
         jlink runtime or jpackage-created runtime
                          |
                          v
            jpackage --type app-image per OS/arch
                          |
                          v
             Run bundled launcher; verify runtime
                          |
                          v
                 Native installer packaging
                          |
                          v
              Sign/notarize + hash + provenance
                          |
                          v
            Fresh-install / upgrade / rollback QA
                          |
                          v
              Staged distribution and monitoring
```

### 9.2. Những dữ liệu nên lưu trong release manifest

- App version hiển thị, native package version/revision, release channel và release date.
- Commit hash, build ID, dependency lockfile/SBOM và checksum package.
- JDK vendor/build, feature/update/patch, runtime image checksum/module list.
- OS + architecture + format gói, signing identity, installer identity/upgrade UUID.
- Mức compile target (`--release`), launcher settings, native dependencies.
- Data schema/migration version, compatibility/rollback notes.
- Advisory/CVE được vá, trạng thái rollout và các thiết bị chưa cập nhật.

Mục đích là trả lời được: **người dùng nào đang có bản ứng dụng nào chứa runtime và dependency nào**. Nhìn lệnh `java -version` ở terminal của họ **không đủ** để xác định runtime nhúng của ứng dụng self-contained.

### 9.3. Ma trận test quan trọng

| Thử nghiệm | Điều phải xác nhận |
| --- | --- |
| Fresh install bản N | Chạy launcher đúng, có runtime nhúng, không phụ thuộc Java hệ thống |
| App build `--release 17` trên runtime mới | Không lỗi class version/API/module/provider |
| N-1 → N | Installer nhận đúng sản phẩm, app/data/settings còn nguyên |
| N-2 → N nếu hỗ trợ | Migration và đường lên bản mới hoạt động |
| Patch-only runtime rebuild | TLS/crypto/locale/timezone/GC/GUI/JNI/service providers vẫn đúng |
| App đang chạy khi cài | Có xử lý file lock, yêu cầu đóng app và trạng thái giao dịch hợp lệ |
| Không đủ quyền hoặc không đủ dung lượng | Không để gói/cấu hình ở trạng thái hỏng |
| Cài đặt bị ngắt | Có phát hiện và phục hồi/rollback rõ ràng |
| Sai OS/architecture | Từ chối gói sai thay vì thay bản đang chạy |
| Chữ ký/hash sai | Updater/installer từ chối |
| Downgrade + schema migration | Khôi phục dữ liệu đúng hoặc ngăn downgrade không an toàn |
| Uninstall/reinstall | Dữ liệu được giữ hoặc xóa theo chính sách |
| OS nền và toolchain thay đổi | Native launcher, shortcuts, services, signing vẫn đúng |

**Smoke test bắt buộc là chạy executable đã package**, không chỉ chạy `java -jar` bằng JVM của CI. Nếu dùng native app GUI, test cửa sổ UI, đường dẫn resource, font/icon và quyền truy cập user data. Với app dùng `ServiceLoader`, test provider thực sự được tìm thấy trong runtime image.

### 9.4. Cập nhật định kỳ và triển khai theo đợt

Một kế hoạch vận hành có thể chọn nhóm nội bộ/canary trước, sau đó nhóm người dùng nhỏ rồi toàn bộ. Theo dõi crash rate, khởi động thất bại, lỗi cài, tỷ lệ runtime cũ, migration failures và hỗ trợ khách hàng. Khi thấy vấn đề, **dừng rollout**, giữ artifact đã ký và có kế hoạch hồi phục dữ liệu.

Đừng bắt mọi thiết bị phải cập nhật cùng lúc nếu có máy offline hoặc yêu cầu công việc không được gián đoạn; tuy nhiên các bản chứa lỗ hổng nghiêm trọng cần chính sách deadline và xử lý thiết bị không tuân thủ.

## 10. Lỗi thường gặp và hướng xử lý

### Lỗi 1: Chỉ nâng Java trong hệ điều hành

Runtime của gói `jpackage` là thành phần riêng; nâng JDK toàn máy không thay nó. **Cách đúng:** đóng gói và phân phối một app-image/installer mới với runtime đã vá.

### Lỗi 2: Đổi `--app-version` rồi nghĩ Java runtime đã đổi

`--app-version` thay metadata app/package; không thay runtime hay JAR. **Cách đúng:** kiểm tra runtime image, app version và classfile target riêng biệt.

### Lỗi 3: Đổi runtime nhưng không tăng version gói

Installer có thể không chấp nhận hoặc không phân biệt bản phát hành mới. **Cách đúng:** tăng package version/revision phù hợp platform, kiểm tra N-1 → N.

### Lỗi 4: Mỗi build Windows lại sinh upgrade UUID mới

Không giữ upgrade identity có thể làm installer coi là sản phẩm khác. **Cách đúng:** sinh một lần và giữ trong release configuration.

### Lỗi 5: Tin `--win-update-url` là auto-updater

Tùy chọn chỉ trỏ tới URL thông tin bản cập nhật. **Cách đúng:** thiết kế downloader, xác minh chữ ký, tiến trình cài đặt và rollback riêng nếu cần.

### Lỗi 6: Tạo gói native mọi OS từ một Windows runner

`jpackage` không hỗ trợ cross-platform native packaging. **Cách đúng:** runner và integration test đúng OS/architecture.

### Lỗi 7: Chỉ có `java.base` trong runtime app thực tế

Image có thể khởi động ở đường đơn giản nhưng lỗi khi gọi desktop/JDBC/TLS/locale. **Cách đúng:** phân tích và test module/provider, đừng tối ưu kích thước trước tính đúng đắn.

### Lỗi 8: Không kiểm tra module service binding trên JDK 25+

Runtime do jpackage tự tạo thay đổi service binding mặc định ở JDK mới. **Cách đúng:** kiểm tra provider và truyền `--bind-services` theo hướng dẫn khi app cần.

### Lỗi 9: Nhầm `--release 17` là runtime Java 17

`--release` kiểm soát compiler target; launcher có thể dùng runtime Java mới hơn. **Cách đúng:** đo Java runtime version từ **packaged launcher/image**.

### Lỗi 10: Hard-code version trong app và nhập version khác cho jpackage

Màn hình About có thể khác metadata installer như demo `2.4.0` và `2.4.1`. **Cách đúng:** sinh version từ một nguồn build duy nhất.

### Lỗi 11: Lưu database/settings trong thư mục install

Installer có thể ghi đè/xóa khi nâng gói. **Cách đúng:** tách mutable user data ra khỏi app image.

### Lỗi 12: Chỉ rollback binary khi schema đã migrate

Ứng dụng cũ không nhất thiết đọc dữ liệu mới. **Cách đúng:** schema-versioned migration và backup/restore đã test.

### Lỗi 13: Sửa signed bundle sau khi ký

Thay runtime hoặc launcher sau signing có thể làm chữ ký vô hiệu. **Cách đúng:** build xong mới ký artifact cuối, verify và phát hành.

### Lỗi 14: Test `java -jar` nhưng không test packaged launcher

Runtime tự sinh bằng `jlink` có thể thiếu module/service provider hoặc khác JVM trên `PATH`. **Cách đúng:** smoke test image thật ở OS tương ứng.

### Lỗi 15: Cập nhật runtime rồi quên thư viện bên thứ ba

Vá JDK không tự sửa CVE trong dependencies hoặc native libs ứng dụng mang theo. **Cách đúng:** SBOM, dependency scanning và release security checks.

### Lỗi 16: Updater tin hash/manifest không có xác thực

Attacker có thể thay cả gói và hash. **Cách đúng:** ký metadata và artifact, xác minh chuỗi tin cậy, ngăn downgrade/replay.

### Lỗi 17: Đổi product identity/install scope không có migration

Bản mới có thể cài song song, mất shortcut hoặc không tìm đúng user data. **Cách đúng:** giữ ID ổn định, chỉ đổi qua kế hoạch migration đã kiểm tra.

### Lỗi 18: Không có chính sách cho người dùng offline lâu ngày

Thiết bị từ N-3 có thể không nâng trực tiếp lên N; bản runtime lỗi vẫn tiếp tục tồn tại. **Cách đúng:** theo dõi fleet version và hỗ trợ các đường upgrade rõ ràng, với deadline bảo mật khi thích hợp.

## 11. Checklist release và bài tập

**Checklist trước khi phân phối:**

- [ ] JDK vendor/build được duyệt, còn nhận bản vá; CVE/JDK advisories đã xem xét.
- [ ] App version, native package revision, Java runtime full version và `--release` được ghi riêng.
- [ ] `jpackage` dùng module hiện hành `jdk.jpackage`; không bật cờ incubator cũ.
- [ ] App UI/About và `--app-version` lấy từ cùng release configuration.
- [ ] Runtime mới đã được tạo, modules/providers/JNI đã test.
- [ ] Native installer có identity ổn định, version hợp lệ, build đúng OS/arch.
- [ ] Packaged launcher đã chạy, tệp runtime release đã đối chiếu.
- [ ] Signing/notarization, artifact hash và provenance đã được xác nhận.
- [ ] Các đường nâng cấp từ phiên bản còn hỗ trợ đã test.
- [ ] Migration dữ liệu có backup và đường rollback đã thử.
- [ ] Installer/updater xử lý mất mạng, thiếu quyền, app đang chạy.
- [ ] Có staged rollout, giám sát, emergency stop và kế hoạch vá khẩn.
- [ ] File/user data nằm ngoài install dir và có chính sách uninstall.
- [ ] Tất cả phụ thuộc và runtime trong SBOM hoặc release manifest đã được rà soát.
- [ ] Không có thông tin nhạy cảm trong update manifest và log cài đặt.

**Bài tập:**

1. Nêu khác nhau giữa `appVersion=2.4.0`, `runtimeVersion=24.0.2` và `--release 17`.
2. Chạy `VersionedDesktop.java`, tạo app-image và xác nhận `runtimeFeature` từ executable trong image.
3. Dùng `--app-version 2.4.1` nhưng giữ JAR cũ: tại sao app vẫn in `2.4.0`?
4. Mô tả các bước khi JDK vendor thông báo security update ảnh hưởng runtime nhúng.
5. Thiết kế release manifest chứa app version, JDK vendor/build, OS/arch, hash và commit.
6. Vì sao Windows `--win-upgrade-uuid` phải được giữ ổn định qua các bản update?
7. Phân biệt `--win-update-url` và một updater có xác minh chữ ký.
8. Nêu cách tạo runtime bằng `jlink` và cách kiểm tra module thiếu.
9. Giải thích thay đổi service bindings trong runtime jpackage JDK 25+.
10. Lên test matrix cho fresh install, N-1→N, downgrade/rollback và uninstall.
11. Khi bản N đã migrate database mà rollback ứng dụng về N-1, cần xử lý gì?
12. Tạo chính sách rollout theo đợt cho bản chỉ sửa runtime có CVE.
13. Với Windows/macOS/Linux, vì sao cần các runner và signing checks riêng?
14. Nếu một device dùng JDK mới trên `PATH` nhưng app-image chạy runtime cũ, ưu tiên kiểm chứng nguồn nào?
15. Nêu rủi ro khi updater tải SHA-256 và installer từ cùng một nguồn không xác thực.

**Đáp án định hướng:** (1) ba trục phiên bản; (2) chạy packaged launcher; (3) jpackage không sửa JAR; (4) chọn JDK đã vá, rebuild, test, sign, rollout; (5) manifest truy vết; (6) stable product upgrade identity; (7) URL thông tin không tự cài; (8) đầy đủ module/service providers; (9) kiểm tra `--bind-services` theo JDK mới; (10) OS-specific upgrade tests; (11) schema migration/restore; (12) canary + deadline + stop; (13) native packages không cross-platform; (14) runtime bên trong image; (15) thay cả hash và installer là một kiểu tấn công chuỗi cung ứng.

## 12. Nguồn tài liệu chính thức còn áp dụng

- **OpenJDK JEP 343 — Packaging Tool (Incubator), Java 14:** https://openjdk.org/jeps/343
- **OpenJDK JEP 392 — Packaging Tool, Java 16:** sự ổn định của `jdk.jpackage`: https://openjdk.org/jeps/392
- **Oracle Java 25 — jpackage Command Reference:** option `--app-version`, `--runtime-image`, các package formats và Windows upgrade URL/UUID: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html
- **Oracle Java 26 — Packaging Overview:** target OS build, runtime embedded và service bindings JDK 25+: https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html
- **Oracle Java 26 — Image and Runtime Modifications:** `jlink`, runtime image tùy chỉnh: https://docs.oracle.com/en/java/javase/26/jpackage/image-and-runtime-modifications.html
- **Oracle Java 26 — Manage the Installation:** install directory, shortcut, license, console: https://docs.oracle.com/en/java/javase/26/jpackage/manage-installation.html
- **Oracle Java 26 — JDK Version-String Format:** feature/update/patch của runtime: https://docs.oracle.com/en/java/javase/26/install/version-string-format.html
- **Oracle Java 27 — jpackage Command Reference:** tiếp tục công bố API/option trên JDK hiện đại: https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html

**Ghi nhớ:** Với `jpackage`, **application version**, **Java runtime nhúng** và **compiler target** có vòng đời độc lập. Muốn vá runtime của gói đã phát hành cần **tạo lại runtime và bộ cài**, đồng bộ application/package metadata, giữ danh tính nâng cấp, ký/kiểm thử native installer, bảo toàn dữ liệu người dùng và phát hành qua cơ chế cập nhật đáng tin cậy.