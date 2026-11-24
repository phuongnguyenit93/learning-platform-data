# Chiến lược build theo từng hệ điều hành, kiến trúc đích

Native executable được tạo cho một hệ điều hành và kiến trúc CPU cụ thể. Binary Linux/AMD64 không thể chạy trực tiếp như binary Windows/x64 hay macOS/ARM64. Ngay cả khi các máy cùng chạy Linux, khác biệt kiến trúc, libc và toolchain cũng có thể khiến artifact không tương thích.

GraalVM Native Image không hỗ trợ cross-compilation theo mô hình tổng quát. Vì vậy, CI/CD cần tổ chức build theo từng platform target. Với Spring Boot, có thể tạo executable JAR đã chứa Spring AOT assets làm artifact trung gian trung lập với OS, sau đó chuyển JAR thành native executable hoặc container image trên worker phù hợp với từng target.

Bài này thiết kế pipeline cho Linux, Windows và macOS trên AMD64/AArch64; phân biệt binary độc lập với container image; cấu hình Maven, Gradle và Buildpacks; tổ chức CI matrix; kiểm thử, cache, lưu artifact và phát hành an toàn.

## 1. Xác định platform target của artifact

Khi phát hành ứng dụng, cần xác định ít nhất ba lớp:

1. **Operating system:** Linux, Windows hoặc macOS.
2. **CPU architecture:** AMD64/x86-64 hoặc AArch64/ARM64.
3. **Runtime ABI và môi trường:** libc, system libraries, native toolchain và các thư viện JNI mà executable cần.

| Target | Định dạng executable phổ biến | Môi trường build cần có |
| --- | --- | --- |
| Linux/AMD64 | ELF x86-64 | GraalVM Native Image, GCC/Clang và Linux headers/libraries |
| Linux/AArch64 | ELF ARM64 | GraalVM hỗ trợ AArch64 và toolchain Linux ARM64 |
| Windows/AMD64 | PE executable | GraalVM hỗ trợ Windows x64, MSVC và Windows SDK |
| macOS/AArch64 | Mach-O ARM64 | GraalVM hỗ trợ macOS ARM64 và Xcode Command Line Tools |

Các target không tạo thành một ma trận đầy đủ. Một distribution GraalVM có thể hỗ trợ Linux/ARM64 nhưng không hỗ trợ Windows/ARM64; release mới có thể bỏ một platform mà release cũ từng hỗ trợ. Chỉ thêm một tổ hợp OS/architecture sau khi xác nhận distribution và version đang chọn có Native Image cho target đó.

### Binary và container image là hai loại artifact khác nhau

- Native executable độc lập mang định dạng của OS đích: ELF, PE hoặc Mach-O.
- Container image chạy trên container runtime tương thích. Với Spring Boot Buildpacks, trường hợp phổ biến là Linux container.
- OCI manifest đa kiến trúc có thể trỏ tới nhiều image như `linux/amd64` và `linux/arm64`. Manifest này không biến một executable AMD64 thành executable ARM64.
- Binary Windows và macOS thường được phát hành như artifact riêng, không nằm trong manifest Linux multi-platform.

Đừng dùng chung một tên file hoặc một tag container cho các binary có target khác nhau nếu pipeline không giữ rõ metadata của từng artifact.

## 2. Vì sao cần worker đúng OS và architecture?

Native Image thực hiện static analysis, biên dịch code và liên kết native executable. Quá trình này sử dụng GraalVM distribution cùng toolchain của môi trường build. Tùy chọn `--target` có thể chọn một số OS/architecture target được toolchain hỗ trợ, nhưng không biến `native-image` thành cross-compiler tổng quát.

Spring Boot cho phép tạo executable JAR đã có AOT-generated assets, sau đó chuyển JAR thành native image trên CI/CD platform phù hợp. JAR là artifact Java có thể chuyển giữa các worker; native executable được tạo riêng trên worker tương ứng với OS/architecture đích.

### Hai cách tổ chức pipeline

**Build từ source trên từng worker**

Mỗi matrix job checkout source, chạy Spring AOT và Native Image trên runner của chính target đó. Cách này dễ triển khai, dễ chẩn đoán và thường phù hợp khi số target ít.

**Build AOT JAR một lần rồi chuyển đổi trên từng worker**

Job đầu tiên compile, test và đóng gói executable JAR có generated classes, resources và reachability metadata. Các job tiếp theo tải JAR đó rồi dùng GraalVM Native Image hoặc Buildpacks trên worker đúng platform.

Cách thứ hai tránh lặp một số bước Java/AOT. Cần bảo đảm JAR thực sự chứa AOT assets và các worker dùng phiên bản JDK/GraalVM tương thích. Chỉ chuyển JAR giữa các job; không chuyển native executable của một platform sang worker khác rồi coi nó là binary tương thích.

## 3. Xác minh ma trận platform được hỗ trợ

Không nên tạo matrix bằng tích Descartes của mọi hệ điều hành và kiến trúc. Trước khi khai báo runner, hãy kiểm tra:

- GraalVM distribution: Oracle GraalVM, GraalVM Community, Mandrel hay Liberica Native Image Kit.
- GraalVM/JDK version và bản cập nhật cụ thể.
- OS version, CPU architecture và trạng thái hỗ trợ của distribution.
- Native Image có được cung cấp cho tổ hợp đó hay không.
- Build toolchain của runner có đủ compiler, linker, headers và SDK.
- Runtime image hoặc môi trường máy đích có tương thích với binary hay không.

Ví dụ, ma trận Oracle GraalVM 25 có thể sử dụng Linux x64, Linux AArch64, Windows x64 và macOS AArch64 khi release tương ứng hỗ trợ các platform đó. macOS x64 đã bị loại khỏi các bản GraalVM mới; Windows ARM64 cũng không nên được thêm chỉ vì CI provider có runner ARM64. Hãy kiểm tra support matrix của distribution trước khi bật job.

### Ví dụ runner trên GitHub Actions

Các label dưới đây là ví dụ runner hiện có trong GitHub Actions; availability, quota và image version còn tùy repository và loại runner:

| Target | Runner ví dụ | Ghi chú |
| --- | --- | --- |
| Linux/AMD64 | `ubuntu-24.04` | Phù hợp build executable Linux x64 |
| Linux/ARM64 | `ubuntu-24.04-arm` | Dùng runner ARM64 thật, không giả lập CPU x64 |
| Windows/AMD64 | `windows-2025` | Kiểm tra Visual Studio Build Tools và Windows SDK |
| macOS/ARM64 | `macos-15` | Runner Apple Silicon; kiểm tra GraalVM distribution hỗ trợ macOS ARM64 |

Nếu CI provider không có runner cho target cần thiết, dùng self-hosted runner hoặc build service phù hợp. Không thay thế việc kiểm thử target bằng cách chỉ đổi biến `--target` trên một runner khác kiến trúc.

## 4. Tách pipeline thành các giai đoạn

Một pipeline dễ bảo trì thường chia thành các giai đoạn sau:

~~~mermaid
flowchart TD
    A["Commit / Pull request"] --> B["JVM compile và unit tests"]
    B --> C["Spring AOT và executable JAR"]
    C --> D["Native build matrix"]
    D --> E["Linux AMD64"]
    D --> F["Linux ARM64"]
    D --> G["Windows x64"]
    D --> H["macOS ARM64"]
    E --> I["Native smoke / integration tests"]
    F --> I
    G --> I
    H --> I
    I --> J["Checksum, SBOM và provenance"]
    J --> K["Publish platform artifacts"]
    I --> L["Build Linux container images"]
    L --> M["AMD64 image + ARM64 image"]
    M --> N["OCI multi-platform manifest"]
    K --> O["Release"]
    N --> O
~~~

**JVM verification** chạy nhanh hơn và phát hiện lỗi compile, unit test, dependency, formatting hoặc static analysis trước khi tiêu tốn tài nguyên native build.

**AOT preparation** tạo executable JAR có generated code và metadata. Với Spring Boot, Spring AOT là bước bắt buộc để chạy ApplicationContext trong native image.

**Native matrix** tạo artifact độc lập trên từng worker. Một job lỗi không nên ngăn các target khác chạy xong, vì log của từng platform giúp khoanh vùng khác biệt.

**Validation và publishing** chỉ diễn ra sau khi artifact đã được kiểm tra. Nếu một target chưa build được hoặc native test thất bại, không tạo release giả định rằng tất cả platform đã sẵn sàng.

## 5. Chuẩn bị toolchain cho từng OS

Native Image cần compiler và các thư viện phát triển của platform build.

### Linux

Trên Ubuntu, môi trường thường cần build-essential và zlib development headers:

~~~bash
sudo apt-get update
sudo apt-get install -y build-essential zlib1g-dev
~~~

Một số distribution còn cần `glibc-devel`, `libstdc++-static` hoặc package tương đương. Hãy dùng hướng dẫn cài đặt của đúng GraalVM release và Linux distribution.

Phân biệt rõ glibc và musl. Binary build với một libc không tự động chạy trên runtime image chỉ cung cấp libc khác. Builder image và run image của Buildpacks cũng cần cùng stack/ABI phù hợp.

### Windows

Native Image trên Windows cần Microsoft Visual C++ compiler phiên bản được GraalVM yêu cầu và Windows SDK. GitHub-hosted Windows runner thường có Visual Studio Build Tools, nhưng cần xác minh toolchain trong image đang dùng:

~~~powershell
java --version
native-image --version
cl
~~~

Nếu `cl` không được tìm thấy, mở đúng Developer Command Prompt hoặc cấu hình môi trường MSVC theo hướng dẫn của runner/GraalVM. Không coi việc cài JDK đơn thuần là đã đủ điều kiện build native.

### macOS

Cài Xcode Command Line Tools:

~~~bash
xcode-select --install
~~~

Sau đó kiểm tra:

~~~bash
java --version
native-image --version
clang --version
xcode-select -p
~~~

GraalVM distribution và version phải hỗ trợ kiến trúc macOS của runner. Một số distribution không còn phát hành Native Image cho macOS Intel; kiểm tra download/support matrix trước khi thêm target này.

## 6. Cấu hình Maven cho native build

Với Maven, Spring Boot Maven Plugin xử lý Spring AOT và GraalVM Native Build Tools thực hiện Native Image compilation. Dự án dùng `spring-boot-starter-parent` có thể sử dụng profile `native` để thiết lập các bước cần thiết.

Ví dụ khai báo hai plugin trong module ứng dụng:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>

        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu plugin không được parent quản lý version, khai báo version tương thích trong dependency/plugin management của dự án. Giữ Spring Boot, GraalVM và Native Build Tools ở các version đã được kiểm tra cùng nhau.

Build native trên runner tương ứng:

~~~bash
./mvnw -B -Pnative package
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd -B -Pnative package
~~~

Với Spring Boot Maven Plugin, profile `native` có thể kích hoạt `process-aot` và cấu hình phù hợp cho Native Build Tools hoặc Buildpacks. Nếu tự tổ chức AOT JAR job riêng, hãy cấu hình bước AOT/package độc lập với execution tạo native executable; tránh vô tình chạy Native Image trong job trung gian vốn chỉ cần JAR.

### Chọn tên artifact rõ ràng

Có thể cấu hình `imageName` của Native Build Tools để tên executable ổn định, ví dụ `orders-api`. Output vẫn phụ thuộc OS:

- Linux/macOS: `target/orders-api`.
- Windows: `target/orders-api.exe`.

Trong CI, đặt artifact name theo cả OS và architecture, ví dụ `orders-api-linux-amd64` hoặc `orders-api-windows-amd64`. Không upload hai file cùng tên vào cùng một artifact mà không giữ metadata target.

## 7. Cấu hình Gradle cho native build

Với Gradle, Native Build Tools cung cấp task `nativeCompile`. Spring Boot Gradle Plugin thực hiện AOT processing khi cấu hình native tương ứng được bật.

Ví dụ khai báo plugin:

~~~kotlin
plugins {
    id("org.springframework.boot")
    id("org.graalvm.buildtools.native")
}
~~~

Build native executable:

~~~bash
./gradlew nativeCompile
~~~

Trên Windows:

~~~powershell
.\gradlew.bat nativeCompile
~~~

Output mặc định thường nằm dưới `build/native/nativeCompile/`; tên binary được suy ra từ cấu hình application/project. Nếu project cần một tên cố định, cấu hình binary trong `graalvmNative` và dùng cùng quy tắc đặt tên ở tất cả matrix jobs.

Ví dụ Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            imageName = "orders-api"
        }
    }
}
~~~

Kiểm tra DSL theo phiên bản Native Build Tools đang dùng. Với project có nhiều binary, chẳng hạn application và native test, cấu hình target và tên artifact riêng cho từng binary.

## 8. Dùng AOT JAR làm artifact trung gian

Một Spring Boot executable JAR có thể chuyển thành native image nếu nó chứa các AOT generated assets, ví dụ generated classes và JSON hints. Cách này cho phép giữ pipeline JVM hiện có, sau đó tạo native executable trong các CI jobs theo platform.

JAR trung gian cần:

- Được build sau khi Spring AOT xử lý application context.
- Đóng gói generated classes và resources.
- Đóng gói reachability metadata cần thiết.
- Được tạo bằng JDK/version tương thích với GraalVM builder được dùng ở bước native.
- Có version và checksum rõ ràng để các matrix jobs tải đúng cùng một đầu vào.

AOT JAR không phải native executable. Nó vẫn là Java archive và có thể dùng làm đầu vào cho các worker khác nhau. Native compiler chạy trên từng worker mới tạo binary OS/architecture-specific.

### Khi nào nên build source ở mỗi matrix job?

Nếu số target ít và thời gian build chấp nhận được, build từ source trên từng worker thường đơn giản hơn. Cách này giảm sự phức tạp của việc trích xuất JAR, truyền AOT assets và quản lý phiên bản builder.

Nếu số target lớn hoặc AOT processing tốn nhiều thời gian, hãy tách AOT JAR job riêng. So sánh tổng thời gian pipeline và độ phức tạp vận hành trước khi chọn.

## 9. Tạo Linux container image bằng Buildpacks

Spring Boot tích hợp Cloud Native Buildpacks qua Maven `spring-boot:build-image` và Gradle `bootBuildImage`. Có thể dùng `pack` để tạo container image từ AOT-processed executable JAR.

Ví dụ:

~~~bash
pack build orders-api:1.0.0 \
  --builder paketobuildpacks/ubuntu-resolute-builder \
  --run-image paketobuildpacks/ubuntu-resolute-run-tiny \
  --path target/orders-api.jar \
  --env BP_NATIVE_IMAGE=true
~~~

`BP_NATIVE_IMAGE=true` yêu cầu Paketo Native Image buildpack tạo native executable. Builder cung cấp GraalVM Native Image và toolchain cần thiết; run image chứa môi trường tối thiểu để chạy ứng dụng.

Với Spring Boot 4.2, tài liệu hiện hành yêu cầu build application bằng ít nhất JDK 25 cho quy trình Buildpacks native, vì Buildpacks dùng phiên bản GraalVM Native Image tương ứng với Java version được dùng để compile. Hãy kiểm tra yêu cầu của Spring Boot và buildpack version đang sử dụng nếu dự án ở release khác.

### Build container theo từng architecture

Tạo Linux/AMD64 image trên Linux/AMD64 worker và Linux/ARM64 image trên Linux/ARM64 worker. Builder image và run image cũng phải hỗ trợ kiến trúc đó. Không mặc định một builder tag có cùng platform variants cho mọi architecture; xác minh manifest của builder/run image trước khi dùng.

Buildpacks tạo Linux container image. Nếu cần executable Windows hoặc macOS độc lập, dùng Native Build Tools trên worker Windows/macOS phù hợp. Không cố dùng Linux Buildpacks để tạo Mach-O hay Windows PE executable.

## 10. Ví dụ CI matrix với GitHub Actions

Ví dụ sau minh họa build bốn target được hỗ trợ bởi GraalVM distribution và runner đã chọn: Linux/AMD64, Linux/ARM64, Windows/AMD64 và macOS/ARM64. Cần điều chỉnh runner label, GraalVM version, plugin version và target theo repository thực tế.

~~~yaml
name: native-artifacts

on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v6

      - uses: graalvm/setup-graalvm@v1
        with:
          version: '25.0'
          distribution: 'graalvm'
          cache: 'maven'
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: JVM verification
        run: ./mvnw -B verify

  native:
    needs: verify
    strategy:
      fail-fast: false
      max-parallel: 2
      matrix:
        include:
          - os: linux
            arch: amd64
            runner: ubuntu-24.04
            binary: target/orders-api

          - os: linux
            arch: arm64
            runner: ubuntu-24.04-arm
            binary: target/orders-api

          - os: windows
            arch: amd64
            runner: windows-2025
            binary: target/orders-api.exe

          - os: macos
            arch: arm64
            runner: macos-15
            binary: target/orders-api

    runs-on: ${{ matrix.runner }}

    steps:
      - uses: actions/checkout@v6

      - uses: graalvm/setup-graalvm@v1
        with:
          version: '25.0'
          distribution: 'graalvm'
          cache: 'maven'
          github-token: ${{ secrets.GITHUB_TOKEN }}
          native-image-job-reports: 'true'

      - name: Build native executable on Unix
        if: runner.os != 'Windows'
        run: ./mvnw -B -Pnative package -DskipTests

      - name: Build native executable on Windows
        if: runner.os == 'Windows'
        shell: pwsh
        run: .\mvnw.cmd -B -Pnative package -DskipTests

      - name: Upload platform artifact
        uses: actions/upload-artifact@v4
        with:
          name: orders-api-${{ matrix.os }}-${{ matrix.arch }}
          path: ${{ matrix.binary }}
          if-no-files-found: error
~~~

Ví dụ giả định POM đã khai báo Spring Boot Maven Plugin, Native Build Tools và profile `native`; `imageName` được cấu hình là `orders-api`. Job `verify` chạy kiểm thử JVM một lần, còn matrix jobs chạy Native Image trên từng runner. `fail-fast: false` giúp các target khác tiếp tục chạy để thu đủ kết quả; `max-parallel` giới hạn số build nặng đồng thời.

`version: '25.0'` minh họa dòng GraalVM LTS. Trong pipeline phát hành, nên pin bản patch đã kiểm thử và cập nhật có chủ đích. Action major tag trong ví dụ cũng nên được pin commit SHA theo chính sách bảo mật supply chain của tổ chức.

Nếu dùng Gradle, thay bước build bằng task `nativeCompile`, rồi điều chỉnh `matrix.binary` theo output path của project.

## 11. Xây dựng OCI multi-platform image

Với Linux container deployment, build và push từng architecture image bằng tag riêng:

~~~text
registry.example.com/orders-api:1.0.0-linux-amd64
registry.example.com/orders-api:1.0.0-linux-arm64
~~~

Sau khi cả hai image đã được push và kiểm thử, tạo manifest chung:

~~~bash
docker buildx imagetools create \
  --tag registry.example.com/orders-api:1.0.0 \
  registry.example.com/orders-api:1.0.0-linux-amd64 \
  registry.example.com/orders-api:1.0.0-linux-arm64
~~~

Kiểm tra manifest:

~~~bash
docker buildx imagetools inspect registry.example.com/orders-api:1.0.0
~~~

Khi client pull tag chung, container runtime chọn image phù hợp với OS/architecture của node. Mỗi image vẫn chứa native executable được build cho đúng platform.

Không thêm Windows/macOS binary vào Linux manifest. Windows container image, nếu dự án có nhu cầu, cần quy trình và base image Windows riêng. Cũng cần nhớ OCI platform metadata thường chỉ biểu diễn OS/architecture; CPU instruction-set baseline vẫn phải được quản lý trong build và deployment policy.

## 12. Kiểm thử trên từng target

Một build thành công chỉ chứng minh compiler đã tạo artifact. Nó chưa chứng minh binary chạy được trên máy đích hoặc mọi luồng ứng dụng hoạt động đúng.

| Lớp kiểm thử | Chạy ở đâu | Mục tiêu |
| --- | --- | --- |
| Unit và integration JVM | Một runner chuẩn | Kiểm tra logic nghiệp vụ và Spring context |
| Spring AOT processing | AOT job hoặc native matrix | Xác nhận BeanFactory và generated code |
| Native build | Từng OS/architecture runner | Xác nhận compiler và linker của target |
| Native smoke test | Cùng platform với binary | Xác nhận executable khởi động và phục vụ luồng cơ bản |
| Native integration test | Runner hoặc test environment đúng target | Kiểm tra reflection, resource, JNI, serialization và network |
| Deployment test | Máy/cluster thực tế | Xác nhận ABI, libc, container runtime và cấu hình production |

Với Gradle Native Build Tools có task `nativeTest`. Với Maven, Spring Boot hỗ trợ profile `nativeTest` kết hợp AOT test processing và goal test của Native Build Tools. Dùng chúng cho các nhánh có rủi ro native, đồng thời giữ phần lớn unit test ở JVM để feedback nhanh.

### Kiểm thử trên runner không cùng kiến trúc

Nếu không thể chạy trực tiếp binary trên runner, dùng máy kiểm thử hoặc cluster có OS/architecture tương ứng. Emulation có thể hữu ích cho một số smoke test, nhưng không thay thế hoàn toàn native hardware test, đặc biệt khi có JNI, CPU-specific code hoặc yêu cầu hiệu năng.

Không chỉ kiểm tra `--version` hoặc việc process khởi động. Hãy gửi request thật, kiểm tra health endpoint, đọc resource, truy cập database/message broker và thực hiện các luồng có dùng reflection hoặc serialization.

## 13. Cache, thời gian build và tính tái lập

Native Image build tiêu tốn CPU, RAM và thời gian. Một pipeline có thể giảm thời gian mà vẫn giữ tính tái lập nếu cache đúng lớp dữ liệu.

### Nên cache

- Maven local repository hoặc Gradle dependency cache.
- Wrapper và plugin downloads.
- Dependency metadata theo đúng build tool.
- Các cache độc lập với native output và có thể tái sử dụng an toàn.

### Không nên chia sẻ tùy tiện

- Native executable được tạo cho OS/architecture khác.
- Native build intermediates giữa GraalVM version khác nhau.
- Cache compiler hoặc object files giữa runner Windows, macOS và Linux.
- Cache được tạo với toolchain, builder hoặc libc không tương thích.

Cache key nên chứa tối thiểu OS, architecture, JDK/GraalVM version, build tool và lock/dependency file hash. Nếu cache chỉ dành cho dependency repository, có thể tái sử dụng rộng hơn; nếu cache chứa output native, phải tách theo platform và toolchain.

### Kiểm soát mức song song

Mỗi Native Image build có thể cần nhiều RAM. Chạy tám target cùng lúc trên runner nhỏ có thể làm build chậm hơn hoặc bị OOM. Dùng `max-parallel`, runner đủ RAM và phân bổ job theo năng lực CI. Ghi lại thời gian build theo target để xác định platform nào là bottleneck.

### Pin toolchain

Để build có thể tái hiện, ghi rõ:

- GraalVM distribution, JDK version và patch.
- Spring Boot version.
- Native Build Tools Maven/Gradle plugin version.
- Maven/Gradle wrapper version.
- OS runner image và architecture.
- C compiler, linker, SDK và libc/runtime stack.
- Buildpack builder/run image tag hoặc digest.
- Native Image build arguments và CPU baseline.

Không dùng `latest` cho builder image hoặc toolchain trong release pipeline nếu chưa có bước cập nhật và kiểm thử có kiểm soát.

## 14. Quản lý artifact, checksum và provenance

Đặt tên artifact để người nhận nhận diện ngay target:

| Artifact name | Ý nghĩa |
| --- | --- |
| `orders-api-linux-amd64` | ELF dành cho Linux x64 |
| `orders-api-linux-arm64` | ELF dành cho Linux ARM64 |
| `orders-api-windows-amd64.exe` | PE executable dành cho Windows x64 |
| `orders-api-macos-arm64` | Mach-O executable dành cho macOS Apple Silicon |
| `orders-api-1.0.0-linux-amd64` | Container image dành cho Linux/AMD64 |

Mỗi artifact nên đi cùng metadata hoặc release manifest ghi source commit, version ứng dụng, target platform, GraalVM version và build timestamp.

Tạo checksum sau khi build:

~~~bash
sha256sum target/orders-api > target/orders-api.sha256
~~~

Trên PowerShell:

~~~powershell
Get-FileHash .\target\orders-api.exe -Algorithm SHA256
~~~

Trong pipeline phát hành, cân nhắc:

- SBOM cho từng binary/container image.
- Provenance gắn source commit, workflow run và toolchain.
- Chữ ký artifact hoặc container image.
- Kiểm tra vulnerability của dependency và base image.
- Lưu build logs/native-image build report cùng release metadata.

Nếu có macOS binary phân phối cho người dùng cuối, xử lý code signing và notarization theo yêu cầu hệ sinh thái Apple. Với Windows, cân nhắc Authenticode signing. Chỉ publish sau khi tất cả target bắt buộc đã qua validation.

## 15. Chẩn đoán lỗi thường gặp trong CI matrix

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `native-image` không tìm thấy | `JAVA_HOME` trỏ tới JDK thường hoặc action chưa cài Native Image | Kiểm tra GraalVM distribution, PATH và `native-image --version` |
| Linux job lỗi thiếu `gcc`/headers | Runner hoặc container thiếu native toolchain | Cài package theo hướng dẫn của GraalVM và OS |
| Windows job lỗi không tìm thấy `cl.exe` | MSVC/Windows SDK chưa sẵn sàng trong shell | Dùng runner image có Build Tools hoặc khởi tạo developer environment |
| macOS job lỗi linker | Xcode Command Line Tools thiếu hoặc không tương thích | Kiểm tra `xcode-select`, `clang` và SDK |
| ARM64 job không có GraalVM download | Distribution/version không phát hành target đó hoặc runner architecture sai | Kiểm tra support matrix, chọn distribution/runner tương thích |
| Binary build thành công nhưng chạy báo sai format | Artifact được tải nhầm OS/architecture | Đặt tên artifact theo target và xác minh file format |
| Linux image chạy trên máy khác distro bị lỗi libc | Builder/run image hoặc native linkage không tương thích | Chọn stack/runtime phù hợp và test trên base image production |
| AOT JAR không tạo được native image | JAR thiếu generated classes hoặc reachability metadata | Kiểm tra Spring AOT processing và nội dung executable JAR |
| Buildpack không chạy native mode | `BP_NATIVE_IMAGE` chưa được bật hoặc builder không hỗ trợ | Kiểm tra buildpack config và builder/run image |
| Chỉ một target thất bại | Khác biệt platform, dependency JNI hoặc support matrix | Đọc log riêng của job và kiểm tra thư viện native |
| Matrix job OOM hoặc timeout | Native build quá nặng hoặc quá nhiều job chạy đồng thời | Tăng RAM, giới hạn parallelism hoặc tối ưu build |
| OCI manifest thiếu ARM64 | Chưa push image ARM64 hoặc manifest được tạo quá sớm | Chờ cả hai image, kiểm tra manifest rồi mới tạo tag chung |

Không sửa lỗi platform bằng cách đổi ngẫu nhiên `--target`. Trước hết xác định runner thực tế, OS/architecture, GraalVM distribution, toolchain và target của artifact.

## 16. Bài thực hành: tạo pipeline cho Linux AMD64, Linux ARM64, Windows và macOS

Giả sử dịch vụ `orders-api` cần phát hành native executable cho Linux x64, Linux ARM64, Windows x64 và macOS ARM64; đồng thời cung cấp container image Linux đa kiến trúc.

Thực hiện:

1. Chọn một GraalVM distribution và version hỗ trợ cả bốn target.
2. Xác minh runner tương ứng có đúng architecture và native toolchain.
3. Cấu hình Spring Boot AOT và Native Build Tools trong Maven hoặc Gradle.
4. Tạo job JVM verification chạy unit/integration tests một lần.
5. Tạo native matrix với bốn tổ hợp OS/architecture được khai báo tường minh.
6. Dùng cùng GraalVM/JDK version và build arguments cho các target cần tương đương.
7. Đặt tên artifact theo OS/architecture, upload binary và checksum riêng.
8. Thêm native smoke/integration test trên runner hoặc máy đích tương ứng.
9. Tạo hai Linux container image bằng Buildpacks trên runner AMD64 và ARM64.
10. Kiểm tra từng image bằng đúng kiến trúc, sau đó tạo OCI multi-platform manifest.
11. Ghi provenance, SBOM, GraalVM version, source commit và builder image digest.
12. Thử cố tình bỏ một runner hoặc thay builder version trong nhánh thử nghiệm; xác nhận pipeline phát hiện thiếu artifact hoặc toolchain mismatch trước khi publish.

### Câu hỏi tự kiểm tra

1. Vì sao một native executable không thể dùng chung cho Linux, Windows và macOS?
2. `--target` có làm Native Image trở thành cross-compiler tổng quát không?
3. Vì sao Spring Boot executable JAR có AOT assets có thể dùng làm artifact trung gian cho nhiều platform?
4. Tại sao phải chạy native build trên worker phù hợp với OS/architecture đích?
5. Vì sao không nên tạo matrix bằng tích Descartes của mọi OS và architecture?
6. Windows Native Image cần compiler và SDK nào?
7. Vì sao macOS Intel có thể không còn được hỗ trợ bởi một GraalVM distribution mới?
8. Buildpacks tạo loại artifact nào và vì sao nó không thay thế Windows/macOS native executable?
9. OCI multi-platform manifest giải quyết điều gì và không giải quyết điều gì?
10. Những dữ liệu nào nên có trong checksum, SBOM và provenance của native release?

**Tiêu chí đạt:** thiết kế được ma trận CI theo các tổ hợp OS/architecture được hỗ trợ; phân biệt AOT JAR với native executable và container image; build trên runner phù hợp; cấu hình Maven/Gradle/Buildpacks; kiểm thử native trên từng target; tạo OCI manifest cho Linux đa kiến trúc; đồng thời phát hành artifact có tên, checksum và provenance rõ ràng.

## Tài liệu chính thức

- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Maven Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html
- Spring Boot — Gradle Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- GraalVM — Native Image: https://www.graalvm.org/latest/reference-manual/native-image/
- GraalVM — Supported Platforms: https://www.graalvm.org/latest/support/
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM — GitHub Actions setup: https://github.com/graalvm/setup-graalvm
- GitHub Actions — Hosted Runners: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- Paketo — Java Native Image Buildpack: https://paketo.io/docs/reference/java-native-image-reference/
