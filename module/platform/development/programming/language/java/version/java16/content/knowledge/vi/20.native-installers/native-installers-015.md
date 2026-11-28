# Build matrix theo hệ điều hành và kiến trúc cho quy trình CI

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Bộ cài ứng dụng. `jpackage` trở thành công cụ đóng gói production-ready từ Java 16, tạo application image và bộ cài native cho Windows, macOS và Linux. Khi phát hành nhiều hệ điều hành hoặc kiến trúc CPU, pipeline cần tạo package trên môi trường đích tương ứng. Bài học hướng dẫn thiết kế build matrix theo cặp OS/architecture, tách build ứng dụng khỏi packaging, chọn runner và toolchain, đặt tên artifact ổn định, chạy smoke test và quản lý ký số trong CI hiện đại.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao native installer phải được tạo trên nền tảng đích.
- Phân biệt OS, architecture, JDK distribution và package format trong build matrix.
- Chọn runner phù hợp cho Windows, macOS, Linux, x64 và ARM64.
- Dùng matrix `include` để chỉ tạo các tổ hợp được hỗ trợ.
- Tách build/test dùng chung khỏi job đóng gói theo nền tảng.
- Dùng `jpackage` để tạo application image và native installer.
- Xác minh runtime được đóng gói phù hợp với kiến trúc đích.
- Đặt tên artifact, lưu checksum và kiểm tra package sau khi tạo.
- Tổ chức signing, notarization và release credentials an toàn.

## 1. Vì sao cần build matrix?

Ứng dụng Java có thể chạy trên nhiều hệ điều hành nhờ JVM, nhưng native installer gắn với nền tảng cụ thể. Người dùng Windows mong đợi MSI hoặc EXE; người dùng macOS có thể nhận DMG hoặc PKG; người dùng Linux thường nhận DEB hoặc RPM.

`jpackage` nhận ứng dụng Java và runtime image để tạo application image tự chứa, sau đó có thể tạo package native theo hệ điều hành. Công cụ sử dụng `jlink` để tạo runtime nếu bạn không truyền runtime image có sẵn. `jpackage` được chuẩn hóa thành công cụ production-ready trong Java 16 qua JEP 392. [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392)

Một build matrix mô tả nhiều cấu hình CI cần chạy. Mỗi cấu hình thường chứa:

- **OS:** Windows, macOS hoặc Linux.
- **Architecture:** x64 hoặc ARM64.
- **Runner:** máy thực thi job có OS và CPU phù hợp.
- **JDK:** distribution, version và architecture của JDK dùng để build/package.
- **Package format:** MSI, EXE, DMG, PKG, DEB hoặc RPM.
- **Toolchain:** công cụ hệ thống cần thiết cho định dạng package.
- **Artifact identity:** tên file hoặc artifact phản ánh đúng target.

Không nên tạo mọi tổ hợp bằng tích Descartes một cách máy móc. Một runner có thể không tồn tại cho một tổ hợp, JDK vendor có thể chưa cung cấp build cho kiến trúc đó, hoặc package format có thể yêu cầu toolchain chỉ có trên một số hệ điều hành. Matrix nên liệt kê rõ các target thực sự được hỗ trợ.

## 2. jpackage và nguyên tắc build trên nền tảng đích

Tài liệu `jpackage` quy định mỗi package format phải được build trên nền tảng mà package đó chạy; công cụ không hỗ trợ cross-platform packaging. Muốn phát hành cho nhiều nền tảng, phải chạy `jpackage` trên từng nền tảng tương ứng. [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html) · [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)

| Target | Package format thường dùng | Môi trường đóng gói |
|---|---|---|
| Windows x64 | `msi`, `exe` | Windows x64 |
| macOS Intel x64 | `dmg`, `pkg` | macOS Intel |
| macOS Apple Silicon ARM64 | `dmg`, `pkg` | macOS ARM64 |
| Linux x64 | `deb`, `rpm` | Linux x64 |
| Linux ARM64 | `deb`, `rpm` | Linux ARM64 |

Với runtime đi kèm ứng dụng, nên dùng JDK và toolchain có kiến trúc phù hợp target. Cách này giúp runtime image, native launcher và package được tạo, chạy thử trên cùng kiến trúc. Cross-compiling hoặc tạo runtime cho kiến trúc khác là một bài toán toolchain riêng; đừng giả định rằng đổi tên artifact hoặc đặt biến `arch=arm64` trên runner x64 sẽ tạo ra package ARM64.

### 2.1. Phân biệt build JAR và native packaging

Một pipeline thường có hai loại công việc:

1. **Build ứng dụng:** compile, test và tạo JAR/module artifact. Phần này có thể chạy một lần trên runner build chung nếu output độc lập với OS/architecture.
2. **Native packaging:** lấy artifact ứng dụng, chạy `jpackage` trên runner phù hợp, tạo runtime và installer cho target cụ thể.

Nếu ứng dụng có native library, JNI, JavaFX native components hoặc dependency chứa binary theo OS/architecture, bước build đầu tiên có thể cũng cần matrix. Trong trường hợp đó, artifact đầu vào cho packaging phải chứa đúng native dependency của từng target.

Đừng gom mọi bước vào một job Linux rồi kỳ vọng job đó tạo được MSI, DMG và DEB. Việc build JAR trên Linux có thể dùng chung; native packaging cần runner đích.

## 3. Chọn runner và architecture

Runner là máy thực thi job CI. Với GitHub Actions, `runs-on` chọn runner label. GitHub duy trì runner image cho nhiều OS và kiến trúc; danh sách label thay đổi theo thời gian, vì vậy cần kiểm tra tài liệu runner trước khi cố định matrix. [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

Một số label hosted runner được tài liệu GitHub công bố tại thời điểm viết bài:

| Nền tảng | Kiến trúc | Ví dụ runner label |
|---|---|---|
| Ubuntu 24.04 | x64 | `ubuntu-24.04` |
| Ubuntu 24.04 | ARM64 | `ubuntu-24.04-arm` |
| Windows Server 2025 | x64 | `windows-2025` |
| Windows 11 ARM | ARM64 | `windows-11-arm` |
| macOS 15 | Intel x64 | `macos-15-intel` |
| macOS 15 | Apple Silicon ARM64 | `macos-15` |

Các label và tình trạng preview/availability phụ thuộc loại repository, khu vực và chính sách dịch vụ. Đặc biệt, runner Windows ARM có thể có trạng thái preview hoặc điều kiện cung cấp riêng. Chỉ thêm target vào release matrix sau khi xác minh runner, JDK distribution, kiến trúc native dependencies và khả năng cài đặt package.

### 3.1. Dùng self-hosted runner khi hosted runner chưa đáp ứng

Có thể dùng self-hosted runner khi cần:

- Một Linux distribution cụ thể để tạo RPM.
- Kiến trúc CPU chưa có hosted runner phù hợp.
- Toolchain ký số hoặc thiết bị phần cứng được quản lý nội bộ.
- Môi trường kiểm thử tích hợp với hệ thống nội bộ.

Gắn label có ý nghĩa cho runner, ví dụ `linux`, `x64`, `rpm`, `release`. Trong workflow, yêu cầu tất cả label cần thiết để job chỉ chạy trên runner đúng loại. Không dùng một self-hosted runner dùng chung tùy tiện cho package release nếu job từ pull request không đáng tin cậy có thể chạy trên nó.

### 3.2. Xác minh kiến trúc thực tế

Không chỉ tin vào tên matrix. Trong job, ghi lại OS, architecture và JDK đang chạy:

```bash
uname -s
uname -m
java -version
jpackage --version
```

Trên Windows, dùng PowerShell để kiểm tra môi trường:

```powershell
$env:PROCESSOR_ARCHITECTURE
java -version
jpackage --version
```

Có thể lưu các thông tin này trong build log hoặc metadata của artifact. Khi có lỗi chỉ xảy ra trên ARM64, dữ liệu runner/JDK giúp phân biệt lỗi ứng dụng với lỗi packaging toolchain.

## 4. Chọn package format và toolchain theo OS

`jpackage` hỗ trợ các kiểu package native sau:

| OS | `--type` | Ghi chú toolchain |
|---|---|---|
| Windows | `msi`, `exe` | Cần WiX Toolset theo yêu cầu của JDK đang dùng |
| macOS | `dmg`, `pkg` | Xcode command line tools cần cho một số thao tác như signing hoặc tùy chỉnh DMG |
| Linux | `deb` | Trên Ubuntu cần `fakeroot` theo tài liệu packaging |
| Linux | `rpm` | Cần công cụ tạo RPM như `rpm-build`; chọn runner/distribution có toolchain phù hợp |

Danh sách định dạng và prerequisite cần kiểm tra theo JDK được chọn. Tài liệu Oracle nêu các yêu cầu Windows WiX, Linux `fakeroot`/`rpm-build` và Xcode command line tools cho các thao tác macOS liên quan. [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)

### 4.1. Linux: DEB và RPM không nhất thiết cùng một runner

Ubuntu runner là lựa chọn tự nhiên để tạo DEB. Với RPM, nên chọn runner Linux có công cụ RPM phù hợp, thường là một runner dựa trên distribution họ RHEL/Fedora hoặc self-hosted image đã cài sẵn `rpm-build`.

Một workflow có thể dùng cùng matrix job nhưng hai target Linux khác nhau:

- Linux x64 + Ubuntu runner + `deb`.
- Linux x64 + runner RPM chuyên dụng + `rpm`.

Nếu cần hỗ trợ nhiều distribution, hãy test installer trên distribution mục tiêu và các phiên bản được hỗ trợ. Một file DEB được tạo thành công không chứng minh nó cài được trên mọi Debian-based distribution.

### 4.2. Windows: chuẩn bị WiX

Để tạo `msi` hoặc `exe`, runner phải có WiX Toolset phù hợp với phiên bản JDK `jpackage` đang sử dụng và executable cần thiết phải nằm trong `PATH`. Nếu job báo thiếu WiX, kiểm tra toolchain trước khi thay đổi câu lệnh `jpackage`.

Không nên cài toolchain mới nhất một cách mù quáng trong mọi job release. Pin phiên bản đã được kiểm thử và ghi nhận trong workflow image hoặc provisioning script để các lần build có thể tái lập.

### 4.3. macOS: build, signing và notarization

Có thể tạo application image hoặc package trên runner macOS. Khi phát hành cho người dùng bên ngoài, quy trình phân phối thường còn cần ký code, ký package và notarize tùy cách phân phối/chính sách bảo mật của macOS.

Signing cần certificate, private key và credentials. Chỉ đưa secrets vào job phát hành đáng tin cậy, chẳng hạn workflow chạy từ protected branch hoặc release tag sau khi được phê duyệt. Không đưa certificate hoặc private key vào repository, log, artifact trung gian hay job chạy code pull request không tin cậy.

## 5. Thiết kế matrix bằng include

Với các target không tạo thành tích Descartes đầy đủ, dùng `matrix.include` để khai báo từng cấu hình hợp lệ:

```yaml
jobs:
  package:
    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        include:
          - os: linux
            arch: x64
            runner: ubuntu-24.04
            package_type: deb

          - os: linux
            arch: arm64
            runner: ubuntu-24.04-arm
            package_type: deb

          - os: macos
            arch: x64
            runner: macos-15-intel
            package_type: dmg

          - os: macos
            arch: arm64
            runner: macos-15
            package_type: dmg

          - os: windows
            arch: x64
            runner: windows-2025
            package_type: msi

    runs-on: ${{ matrix.runner }}
```

Mỗi object trong `include` là một target hoàn chỉnh. Không cần tạo Windows ARM64 chỉ vì Linux ARM64 có runner; chỉ thêm khi JDK, native dependencies và `jpackage` trên target đó đã được xác minh.

`fail-fast: false` giúp các target khác tiếp tục chạy khi một target lỗi. `max-parallel` giới hạn số job chạy đồng thời, giúp kiểm soát chi phí, giới hạn runner và tải lên dịch vụ ký số.

### 5.1. Khi nào dùng matrix axis và khi nào dùng include?

Dùng axis khi mọi giá trị kết hợp được với nhau. Ví dụ, nếu một test Java thuần chạy giống nhau trên mọi OS và JDK version, có thể dùng:

```yaml
strategy:
  matrix:
    os: [ubuntu-24.04, windows-2025, macos-15]
    java: ['21', '25']
```

Dùng `include` khi cần ghép OS, architecture, runner và package format thành các cặp cụ thể. Với native packaging, `include` thường dễ kiểm soát hơn vì không phải mọi OS đều có cùng package type hoặc architecture.

## 6. Tách build/test dùng chung khỏi packaging matrix

Pipeline nên tạo artifact ứng dụng một lần, kiểm thử nó, sau đó chuyển artifact tới từng job packaging. Điều này giúp mọi package được tạo từ cùng một phiên bản JAR và tránh mỗi runner tự build ra binary khác nhau ngoài ý muốn.

Ví dụ dưới đây dùng Maven và GitHub Actions. Hãy thay tên JAR, main class, version và action version theo dự án của bạn.

```yaml
name: native-installers

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '25'
          cache: maven

      - name: Build and test
        run: mvn --batch-mode clean verify

      - name: Prepare packaging input
        run: |
          mkdir -p staging
          cp target/acme-desk.jar staging/app.jar

      - name: Upload application input
        uses: actions/upload-artifact@v4
        with:
          name: app-input
          path: staging/
          if-no-files-found: error
          retention-days: 3

  package:
    needs: build
    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        include:
          - os: linux
            arch: x64
            runner: ubuntu-24.04
            type: deb
          - os: linux
            arch: arm64
            runner: ubuntu-24.04-arm
            type: deb
          - os: macos
            arch: x64
            runner: macos-15-intel
            type: dmg
          - os: macos
            arch: arm64
            runner: macos-15
            type: dmg
          - os: windows
            arch: x64
            runner: windows-2025
            type: msi

    runs-on: ${{ matrix.runner }}
    steps:
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '25'

      - uses: actions/download-artifact@v4
        with:
          name: app-input
          path: staging

      - name: Verify packaging tools
        shell: bash
        run: |
          java -version
          jpackage --version
          mkdir -p dist

      - name: Build application image
        shell: bash
        run: |
          jpackage --type app-image \
            --name AcmeDesk \
            --app-version 1.4.0 \
            --vendor "Example Company" \
            --input staging \
            --main-jar app.jar \
            --main-class com.example.Main \
            --dest app-image

      - name: Smoke test application image
        shell: bash
        run: |
          case "${{ matrix.os }}" in
            linux)
              ./app-image/AcmeDesk/bin/AcmeDesk --self-test
              ;;
            macos)
              ./app-image/AcmeDesk.app/Contents/MacOS/AcmeDesk --self-test
              ;;
            windows)
              ./app-image/AcmeDesk/AcmeDesk.exe --self-test
              ;;
          esac

      - name: Build native installer
        shell: bash
        run: |
          jpackage --type "${{ matrix.type }}" \
            --name AcmeDesk \
            --app-version 1.4.0 \
            --vendor "Example Company" \
            --input staging \
            --main-jar app.jar \
            --main-class com.example.Main \
            --dest dist

      - name: Upload native installer
        uses: actions/upload-artifact@v4
        with:
          name: AcmeDesk-${{ matrix.os }}-${{ matrix.arch }}-${{ matrix.type }}
          path: dist/*
          if-no-files-found: error
          retention-days: 14
```

Đây là skeleton cần điều chỉnh theo runner image, toolchain, đường dẫn output và yêu cầu ứng dụng. Đặc biệt:

- Runner Windows phải có WiX phù hợp; runner Linux phải có prerequisite cho DEB/RPM.
- Lệnh `--self-test` là giao diện ví dụ của ứng dụng. Hãy triển khai chế độ tự kiểm tra thoát nhanh hoặc thay bằng lệnh smoke test tương ứng.
- Nếu ứng dụng cần resource ngoài JAR, hãy đưa chúng vào `staging` và kiểm tra chúng có được đóng gói.
- Nếu `main-class` đã có trong manifest, vẫn nên khai báo rõ ràng trong pipeline để cấu hình dễ đọc và tái lập.
- Pin action theo commit SHA trong pipeline release được bảo vệ nếu chính sách supply-chain của tổ chức yêu cầu; tag major trong ví dụ chỉ để dễ đọc.

### 6.1. Vì sao job package cần setup JDK riêng?

Mỗi job matrix thường chạy trên runner mới, không chia sẻ filesystem với job build. Vì vậy job package cần cài JDK riêng để có `jpackage` và `jlink`. Artifact JAR được truyền qua artifact storage của CI, không dựa vào thư mục `target` của job build.

Nên thống nhất JDK vendor/version giữa các target để runtime image và hành vi packaging dễ dự đoán. Nếu mục tiêu là tương thích bytecode với Java cũ, cấu hình compiler `--release` riêng; không nhầm compiler target với version runtime được `jpackage` đóng gói. Ứng dụng compile bằng `--release 16` nhưng đóng gói với JDK 25 sẽ đi kèm runtime JDK 25 nếu `jpackage` tạo runtime từ JDK đó.

## 7. Dùng app-image làm bước kiểm thử trước installer

`--type app-image` tạo cấu trúc ứng dụng có launcher và runtime mà không cần tạo installer cuối cùng. Đây là artifact tốt để kiểm tra nhanh trên đúng OS/architecture trước khi chạy bước package. Tài liệu Oracle cũng khuyến nghị application image như cách kiểm tra ứng dụng trước khi tạo installable package. [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)

Smoke test nên xác minh:

- Launcher chạy được trên runner target.
- Runtime đi kèm có thể khởi động ứng dụng.
- Module/JAR và resource được đưa vào image.
- JVM options và application arguments được truyền đúng.
- Ứng dụng có thể chạy một thao tác đơn giản rồi thoát.
- Không cần `JAVA_HOME` hoặc JDK cài toàn cục của runner để launch.

Không chỉ kiểm tra file package tồn tại. Một MSI hoặc DMG được tạo thành công vẫn có thể chứa launcher sai đường dẫn, thiếu resource hoặc runtime không tương thích.

### 7.1. Kiểm thử installer thực tế

Smoke test application image chưa chứng minh installer cài đặt đúng. Trên mỗi OS, nên có bước cài thử trong môi trường sạch:

- Windows: cài MSI/EXE, kiểm tra shortcut/uninstall và chạy launcher đã cài.
- macOS: mount DMG hoặc cài PKG, kiểm tra app bundle, signature và khả năng launch.
- Linux: cài DEB/RPM trong VM hoặc container phù hợp, kiểm tra dependency, launcher và uninstall.

Việc cài package có thể yêu cầu quyền hệ thống. Dùng VM/container dùng một lần hoặc runner test riêng để tránh làm thay đổi máy runner được tái sử dụng.

## 8. Artifact naming và metadata

Khi matrix chạy song song, artifact name phải phân biệt được OS, architecture, format và version. Một mẫu dễ đọc:

```text
AcmeDesk-1.4.0-windows-x64-msi
AcmeDesk-1.4.0-macos-arm64-dmg
AcmeDesk-1.4.0-macos-x64-dmg
AcmeDesk-1.4.0-linux-x64-deb
AcmeDesk-1.4.0-linux-arm64-deb
```

Không đặt mọi output thành `installer.zip` hoặc `app.zip` rồi upload cùng tên. Tùy CI provider, artifact trùng tên có thể bị ghi đè, ghép hoặc gây lỗi.

Mỗi artifact nên đi kèm metadata có thể truy vết:

- Version ứng dụng và commit SHA.
- OS, architecture và package format.
- JDK vendor/version/architecture.
- Phiên bản `jpackage` và toolchain native.
- Thời gian build và workflow run ID.
- Checksum SHA-256.
- Trạng thái smoke test và signing.

Ví dụ tạo checksum trên Linux/macOS:

```bash
sha256sum dist/*
```

Trên Windows có thể dùng PowerShell:

```powershell
Get-FileHash .\dist\* -Algorithm SHA256
```

Lưu checksum cạnh artifact hoặc trong manifest phát hành. Checksum giúp phát hiện file thay đổi trong quá trình lưu trữ/phân phối; nó không tự xác minh danh tính người phát hành. Để xác minh nguồn gốc, kết hợp signing và provenance theo chính sách tổ chức.

## 9. Quản lý signing và notarization trong CI

Native installer có thể cần ký số để người dùng xác minh nhà phát hành và giảm cảnh báo bảo mật. Quy trình cụ thể khác theo nền tảng:

| OS | Việc thường cần | Bí mật/credential |
|---|---|---|
| Windows | Ký executable và installer | Code-signing certificate, private key hoặc signing service token |
| macOS | Code signing, package signing và notarization tùy kênh phân phối | Developer ID certificate, keychain credentials, App Store Connect API key |
| Linux | Ký repository/package metadata tùy phương thức phân phối | GPG/private signing key hoặc signing service |

Không lưu private key trong source repository. Dùng CI secret store hoặc signing service; giới hạn quyền đọc secret cho protected release workflow. Pull request từ fork không được nhận credential phát hành.

Nên tách pipeline thành:

1. Pull request: build, test, app-image smoke test, không signing.
2. Merge vào protected branch: tạo package thử nghiệm không ký hoặc ký bằng certificate test.
3. Release tag được bảo vệ: tạo package release, ký, notarize nếu cần, xác minh signature và upload artifact cuối.

Signing thường làm artifact thay đổi nội dung; vì vậy checksum phát hành phải được tạo sau bước ký/notarize cuối cùng. Lưu cả log signing và kết quả xác minh.

## 10. Build matrix cho package format bổ sung

Một OS có thể tạo nhiều định dạng. Ví dụ Linux có DEB và RPM; Windows có MSI và EXE; macOS có DMG và PKG. Không nên mặc định mọi format dùng chung toolchain.

Có thể mở rộng matrix bằng một trường `type`:

```yaml
matrix:
  include:
    - os: linux
      arch: x64
      runner: ubuntu-24.04
      type: deb

    - os: linux
      arch: x64
      runner: rocky-linux-x64
      type: rpm

    - os: windows
      arch: x64
      runner: windows-2025
      type: msi

    - os: windows
      arch: x64
      runner: windows-2025
      type: exe

    - os: macos
      arch: arm64
      runner: macos-15
      type: dmg

    - os: macos
      arch: arm64
      runner: macos-15
      type: pkg
```

`rocky-linux-x64` trong ví dụ là tên runner tự quản lý, không phải GitHub-hosted label mặc định. Hãy thay bằng label của self-hosted runner có `rpm-build` và JDK đúng kiến trúc.

Nếu cùng một runner cần tạo hai format, có thể dùng hai matrix entry hoặc một job chạy `jpackage` hai lần. Hai entry độc lập dễ quan sát lỗi và retry riêng; một job có thể tiết kiệm thời gian cài JDK/toolchain. Chọn theo khả năng tái sử dụng toolchain và yêu cầu tách biệt release artifact.

## 11. Tối ưu thời gian, cache và tính tái lập

Build matrix có thể tiêu tốn nhiều phút runner. Tối ưu bằng cách phân tách phần tốn kém:

- Chỉ build/test JAR một lần nếu output portable.
- Cache dependency Maven/Gradle theo lockfile hoặc cấu hình dependency.
- Truyền artifact đã build thay vì checkout/build lại trong mọi job.
- Chỉ chạy packaging matrix đầy đủ trên protected branch hoặc release tag nếu pull request không cần mọi installer.
- Dùng `max-parallel` để tránh quá tải runner hoặc signing service.
- Giữ toolchain version ổn định và ghi nhận trong metadata.
- Dùng `fail-fast: false` để có báo cáo của tất cả target khi cần chẩn đoán matrix.

Không cache output native installer một cách thiếu điều kiện. Cache key cần bao gồm OS, architecture, JDK version, package type và các yếu tố ảnh hưởng output. Nếu không, artifact tạo cho Linux x64 có thể bị dùng nhầm cho ARM64 hoặc package format khác.

Với release quan trọng, ưu tiên runner sạch và tái lập. Cache dependency có thể tăng tốc; không nên tái sử dụng thư mục cài đặt, file signing hoặc output cũ không xác định nguồn gốc.

## 12. Kiểm tra tính tương thích của runtime

`jpackage` có thể tạo runtime image bằng `jlink` từ JDK đang chạy. Runtime image chứa các module cần thiết theo ứng dụng và dependency. Với ứng dụng modular, runtime được tạo từ main module cùng closure dependency; với ứng dụng classpath, cách chọn module runtime khác. [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)

Các câu hỏi cần xác minh trong mỗi target:

- JDK distribution có cung cấp build cho OS/architecture này không?
- Runtime image có đúng kiến trúc với runner và máy người dùng không?
- Native library có đúng định dạng và kiến trúc không?
- Có module JDK nào cần thêm vào runtime image không?
- Ứng dụng có dùng reflection/service loading cần cấu hình bổ sung không?
- Runtime có hỗ trợ đúng hệ điều hành tối thiểu mà bạn công bố không?

Nếu ứng dụng dùng `ServiceLoader` hoặc service binding, kiểm tra hành vi `jlink`/`jpackage` của JDK đang dùng và cấu hình binding theo tài liệu phiên bản đó. Không sao chép cấu hình từ một JDK cũ mà không xác minh trên JDK hiện tại.

### 12.1. Java 16 là mốc tính năng, không phải lựa chọn runtime mặc định

`jpackage` được đưa thành công cụ production-ready trong Java 16, nhưng Java 16 là bản phát hành không phải LTS và đã hết vòng hỗ trợ thông thường. Với pipeline sản xuất hiện nay, nên dùng JDK còn được vendor hỗ trợ, thường là một bản LTS phù hợp với ứng dụng. Nếu cần tương thích bytecode, cấu hình compiler release riêng; đừng buộc runtime đóng gói phải là Java 16 chỉ vì đang học tính năng được giới thiệu ở Java 16.

Kiểm tra chính sách hỗ trợ của JDK vendor và hệ điều hành mục tiêu trước mỗi chu kỳ phát hành. Việc một installer được tạo thành công không chứng minh runtime bên trong còn được cập nhật bảo mật.

## 13. Lỗi thường gặp khi xây dựng matrix

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo mọi tổ hợp OS × architecture | Matrix sinh target không có runner/JDK | Khai báo từng cặp bằng `include` |
| Chạy mọi `jpackage` trên Linux | Không tạo được installer native cho Windows/macOS | Đóng gói trên runner của target |
| Chỉ đổi tên artifact thành ARM64 | Runtime vẫn có thể là x64 | Dùng runner và JDK đúng kiến trúc |
| Build JAR riêng trong từng job | Package có thể đến từ source/build khác nhau | Build một lần và truyền artifact |
| Không cài prerequisite native | `jpackage` thất bại khi tạo package | Kiểm tra WiX, fakeroot, rpm-build, Xcode tools |
| Chỉ kiểm tra installer file tồn tại | Package có thể cài nhưng launcher không chạy | Smoke test app-image và install test |
| Dùng chung artifact name | Output matrix bị trùng hoặc ghi đè | Đưa OS/arch/type/version vào tên |
| Đưa signing secret vào PR job | Credential có thể bị lộ qua code không tin cậy | Chỉ ký trong protected release workflow |
| Không ghi nhận JDK/toolchain | Khó tái hiện lỗi của một target | Lưu version và runner metadata |
| Dùng JDK 16 làm runtime sản xuất mặc định | Runtime không còn nhận cập nhật bảo mật thông thường | Chọn JDK còn được hỗ trợ |

## 14. Checklist trước khi phát hành bộ cài đa nền tảng

Trước khi tạo release:

1. Đã xác định danh sách OS và architecture người dùng cần chưa?
2. Mỗi target có runner thật sự phù hợp không?
3. JDK distribution có hỗ trợ OS/architecture đó không?
4. `jpackage` chạy trên target platform tương ứng chưa?
5. Package format có prerequisite đúng phiên bản chưa?
6. Ứng dụng đã build/test một lần và artifact được truyền rõ ràng chưa?
7. Application image có chạy được trên runner target không?
8. Installer đã được cài thử trên môi trường sạch chưa?
9. Runtime đi kèm có đúng kiến trúc và module cần thiết không?
10. Artifact name có OS, architecture, format và version không?
11. Checksum được tạo sau bước signing cuối cùng chưa?
12. Signing/notarization secret chỉ có trong protected release job không?
13. Runner/JDK/toolchain version đã được ghi nhận chưa?
14. Có kế hoạch loại bỏ artifact hoặc runner không còn được hỗ trợ không?

## 15. Bài tập vận dụng

**Bài 1 — Matrix tối thiểu:** Tạo matrix gồm Windows x64, macOS ARM64 và Linux x64. Gắn runner label, package format và artifact name riêng cho từng target.

**Bài 2 — Include và exclude:** Tạo một matrix có OS và JDK version. Thêm `exclude` cho tổ hợp không hỗ trợ, sau đó viết lại bằng `include` để chỉ giữ target thực sự phát hành.

**Bài 3 — Tách build/package:** Tạo job build Maven một lần, upload JAR, sau đó tạo ba job package độc lập. Xác minh tất cả package nhận cùng commit và cùng JAR checksum.

**Bài 4 — Smoke test:** Tạo app-image cho mỗi OS/architecture và chạy một lệnh `--self-test` thoát nhanh. Sau đó mới tạo installer.

**Bài 5 — Release signing:** Thiết kế workflow chỉ chạy signing khi release tag được bảo vệ. Tạo checksum sau khi ký và lưu metadata JDK/runner cùng artifact.

---

## Tài liệu tham khảo

- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` trở thành công cụ production-ready trong Java 16.
- [Packaging Overview — Java SE 16](https://docs.oracle.com/en/java/javase/16/jpackage/packaging-overview.html): prerequisite và quy tắc build trên nền tảng đích.
- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html): package type, runtime image và các tùy chọn hiện hành.
- [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html): application image, native package và toolchain theo nền tảng.
- [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): runner labels, hệ điều hành và architecture.
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): matrix include, exclude, fail-fast và max-parallel.
- [Choosing the runner for a job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job): lựa chọn runner hosted/self-hosted và kiến trúc.

---

**Ghi nhớ:** Build matrix native installer phải phản ánh các target thật sự được hỗ trợ, không phải mọi tổ hợp OS/CPU có thể tưởng tượng. Hãy build ứng dụng một lần nếu artifact portable, sau đó chạy `jpackage` trên runner có OS và architecture phù hợp, smoke test application image, tạo installer, ký số trong release job được bảo vệ và lưu artifact với metadata truy vết rõ ràng.
