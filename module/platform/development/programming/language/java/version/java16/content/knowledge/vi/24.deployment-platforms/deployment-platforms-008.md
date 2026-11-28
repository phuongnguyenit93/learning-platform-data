# Chọn JDK, công cụ bản địa và image nền nhất quán trong CI

Một pipeline CI đa nền tảng cần thống nhất JDK, compiler, native toolchain và image nền theo đúng target triển khai. Nếu các thành phần này lệch nhau, ứng dụng có thể biên dịch thành công nhưng không chạy được ở production, đặc biệt khi có JNI/JNA, Java agent native, thư viện `.so`/`.dll` hoặc khi build trên x64 để chạy trên ARM64.

“Nhất quán” không có nghĩa mọi stage phải dùng cùng một image hoặc cùng một binary. Nó có nghĩa mỗi artifact được tạo bằng bộ công cụ phù hợp với target mà artifact đó sẽ chạy, các ranh giới giữa build platform và target platform được khai báo rõ, và kết quả được kiểm thử trong môi trường runtime tương ứng.

## 1. Xác định target trước khi chọn công cụ

Trước khi viết CI workflow, hãy xác định ma trận nền tảng mà ứng dụng cam kết hỗ trợ. Mỗi target cần ghi rõ ít nhất:

- Hệ điều hành và phiên bản tối thiểu.
- Kiến trúc CPU, ví dụ `amd64`/`x86_64` hoặc `arm64`/`aarch64`.
- C library/ABI trên Linux, ví dụ glibc hay musl.
- Phiên bản Java tối thiểu mà ứng dụng hỗ trợ.
- Nhà cung cấp và phiên bản JDK dùng để build, test và chạy.
- Native dependencies và toolchain cần thiết cho target.
- Loại artifact phát hành: JAR, runtime image, application image, container image hay installer.

Ví dụ một ma trận triển khai có thể là:

| Target | JDK/runtime | Native toolchain | Image nền |
|---|---|---|---|
| Linux x64, glibc | Linux x64 JDK/JRE | GCC/Clang target x86-64, sysroot glibc phù hợp | Linux image dùng glibc |
| Linux ARM64, glibc | Linux ARM64 JDK/JRE | GCC/Clang target AArch64, sysroot glibc phù hợp | Linux image dùng glibc |
| Linux ARM64, musl | Linux ARM64 musl JDK/JRE | Toolchain target AArch64-musl | Alpine hoặc image musl được duy trì |
| Windows x64 | Windows x64 JDK/JRE | MSVC x64 và Windows SDK tương ứng | Windows base image phù hợp nếu đóng gói container |
| Windows ARM64 | Windows ARM64 JDK/JRE | MSVC ARM64 và Windows SDK tương ứng | Windows ARM64 base image phù hợp |
| macOS ARM64 | macOS ARM64 JDK/JRE | Xcode/Clang và macOS SDK tương ứng | Runtime và installer cho macOS ARM64 |

Không phải dự án nào cũng cần mọi target trên. Chỉ đưa vào ma trận những nền tảng được sản phẩm cam kết hỗ trợ và có runner/test environment để xác minh.

## 2. Phân biệt build platform và target platform

**Build platform** là máy hoặc container thực hiện pipeline. **Target platform** là môi trường mà artifact cuối cùng sẽ chạy. Hai nền tảng có thể giống nhau hoặc khác nhau.

Ví dụ:

- Build trên Linux x64, tạo JAR Java thuần rồi chạy trên Linux ARM64: thường khả thi vì JAR chứa bytecode portable.
- Build JNI trên Linux x64 rồi chép `.so` x64 sang Linux ARM64: không hợp lệ nếu không có cross-compiler tạo binary AArch64.
- Build JAR trên Windows rồi dùng JDK Linux ARM64 để chạy: thường được nếu JAR và dependency tương thích.
- Tạo `jlink` runtime trên Windows x64 rồi copy sang Linux ARM64: không hợp lệ vì runtime chứa binary của nền tảng build.

Đối với mã Java thuần, có thể build một JAR dùng chung rồi chạy test trên nhiều target. Đối với native code, runtime image hoặc installer, phải tạo artifact theo từng target bằng runner native hoặc quy trình cross-build được công cụ và nhà cung cấp hỗ trợ rõ ràng.

## 3. Chọn JDK cho build và runtime

Chọn JDK dựa trên phiên bản Java mà ứng dụng hỗ trợ, yêu cầu của build tool, chính sách hỗ trợ của nhà cung cấp và kiến trúc đích. Với dự án mới, ưu tiên một bản LTS còn được duy trì; ví dụ Java 21 hoặc Java 25 tùy mức tương thích của framework, plugin, agent và dependency. Không chọn Java 16 cho production mới chỉ vì module này học các thay đổi được giới thiệu ở Java 16.

Một pipeline có thể dùng các JDK khác nhau cho các vai trò:

| Vai trò | Cần xác định |
|---|---|
| Build JVM | JDK dùng để chạy Maven/Gradle và plugin của build |
| Compiler toolchain | JDK cung cấp `javac` để biên dịch mã nguồn |
| Test runtime | JDK dùng chạy unit/integration test |
| Production runtime | JDK/JRE hoặc runtime image thực tế chạy ứng dụng |
| Native build tools | Compiler, linker, SDK, sysroot và toolchain theo target |

Các phiên bản này không nhất thiết phải giống hệt nhau, nhưng cần có chính sách tương thích được ghi rõ. Ví dụ, build tool có thể chạy trên JDK 25 trong khi compiler toolchain dùng JDK 21 và `--release 21`; production runtime phải hỗ trợ class-file và API mà ứng dụng phát hành.

Ngoài version, cần chốt vendor khi ứng dụng phụ thuộc vào bản phân phối cụ thể, Java Flight Recorder, crypto provider, font, CA certificates, JavaFX hoặc chính sách hỗ trợ thương mại. Nếu không có lý do bắt buộc, ưu tiên JDK phân phối chuẩn, có cập nhật bảo mật và ma trận nền tảng được công bố.

## 4. Cố định mức Java bằng --release

Tùy chọn `--release` xác định mức ngôn ngữ Java, class-file version và tập API Java được phép dùng khi biên dịch. Nó giúp tránh tình trạng build trên JDK mới vô tình dùng API không có trong runtime tối thiểu.

Ví dụ biên dịch cho Java 21:

```sh
javac --release 21 -d build/classes src/main/java/com/example/Main.java
```

Với Maven, khai báo release trong cấu hình compiler plugin hoặc property tương ứng:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Với Gradle Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

`--release` không chọn kiến trúc CPU, libc hoặc ABI cho native library. Nó cũng không tự chọn JDK vendor. Các yếu tố đó phải được cấu hình trong toolchain và target build riêng.

## 5. Dùng toolchain rõ ràng trong Maven và Gradle

Không nên dựa hoàn toàn vào JDK đầu tiên tìm thấy trên `PATH`. IDE, shell, Maven wrapper, Gradle daemon và CI runner có thể dùng các JDK khác nhau.

### Maven Toolchains

Maven Toolchains cho phép build chọn một JDK phù hợp với yêu cầu mà không cần dựa vào JDK đang chạy Maven. Cấu hình JDK được khai báo trong `toolchains.xml` trên runner hoặc được cấp qua cơ chế quản lý toolchain của CI.

Ví dụ cấu hình toolchain trên runner:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Build có thể dùng Maven Toolchains Plugin để chọn toolchain, còn `maven-compiler-plugin` sử dụng JDK đã chọn. Đường dẫn `jdkHome` phải là JDK đúng kiến trúc của runner/target build tương ứng; không chia sẻ cấu hình đường dẫn của máy cá nhân cho mọi runner.

### Gradle Java Toolchains

Gradle có thể tự chọn JDK theo language version:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 21
}
```

Nếu cần cố định vendor, có thể khai báo `JvmVendorSpec` phù hợp. Cần kiểm tra Gradle version và cơ chế provision toolchain của tổ chức để bảo đảm runner thực sự có đúng JDK. Build JVM dùng để chạy Gradle vẫn là một yếu tố riêng; Gradle wrapper và JDK chạy Gradle phải đáp ứng yêu cầu của phiên bản Gradle đang dùng.

## 6. Khóa native toolchain theo target

Nếu dự án có C/C++ JNI, native agent hoặc executable phụ trợ, cần cố định toolchain và SDK theo target. Các thành phần thường phải quản lý gồm:

- Compiler và linker: GCC, Clang/LLVM hoặc MSVC.
- Target triple và kiến trúc: x86-64, AArch64, Windows ARM64...
- Sysroot hoặc SDK: header, library và API tối thiểu của hệ điều hành đích.
- ABI và C library: glibc, musl, MSVC runtime hoặc macOS SDK.
- Build system: CMake, Ninja, Make hoặc MSBuild.
- Phiên bản compiler, linker, SDK và dependency native.

Ví dụ, build JNI cho Linux ARM64 musl cần toolchain tạo ELF AArch64 liên kết với musl và các thư viện target tương ứng. Dùng GCC mặc định trên Ubuntu x64 thường sẽ tạo binary x64 glibc; đổi tên file hoặc copy vào Alpine ARM64 không làm binary trở thành AArch64-musl.

Với Windows ARM64, phải dùng compiler/linker target ARM64 và kiểm tra PE machine type. Với macOS, native artifact cần đúng kiến trúc và macOS SDK deployment target. Không chỉ pin compiler version; cần pin cả SDK/sysroot vì chúng quyết định API và ABI mà binary yêu cầu.

## 7. Giữ image nền build và runtime tương thích

Trong Docker multi-stage build, build stage có thể chứa JDK và compiler; runtime stage chỉ chứa JRE/runtime cùng dependency cần thiết. Tuy nhiên, nếu build stage tạo native library, runtime stage phải cung cấp ABI và thư viện tương thích với binary đó.

Với Linux, cần chú ý glibc và musl. Ví dụ, `.so` build trên Ubuntu glibc không mặc nhiên chạy trên Alpine musl. Nếu native library build cho glibc, hãy dùng runtime image glibc phù hợp. Nếu muốn runtime Alpine, hãy build hoặc lấy binary musl tương thích.

Ví dụ Dockerfile dùng các image được truyền từ pipeline:

```dockerfile
ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${BUILD_IMAGE} AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -DskipTests package

FROM ${RUNTIME_IMAGE} AS runtime
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Pipeline cần truyền `BUILD_IMAGE` và `RUNTIME_IMAGE` theo cùng target. Ví dụ, một cặp image JDK/JRE cùng vendor, cùng major Java, cùng kiến trúc và cùng họ base OS giúp giảm rủi ro sai lệch. Nếu build native code, build image phải có toolchain cho target ABI và output phải được kiểm tra trước khi copy.

Với ứng dụng Java thuần, có thể build JAR trên một image khác target rồi copy sang runtime image, miễn compiler/toolchain và API được khóa đúng. Với native code, phải dùng native runner hoặc cross-compiler/sysroot phù hợp và test trong runtime image cuối cùng.

## 8. Xây dựng CI matrix theo OS, CPU và libc

Ma trận CI cần đại diện cho các target được hỗ trợ, không chỉ các hệ điều hành mà nhóm phát triển đang dùng. Một matrix mẫu:

```yaml
strategy:
  fail-fast: false
  matrix:
    include:
      - target: linux-x64-glibc
        runner: self-hosted-linux-x64
        java-arch: x64
        libc: glibc
      - target: linux-arm64-musl
        runner: self-hosted-linux-arm64
        java-arch: aarch64
        libc: musl
      - target: windows-arm64
        runner: self-hosted-windows-arm64
        java-arch: aarch64
        libc: none
```

Tên runner ở ví dụ là nhãn do tổ chức tự cấu hình; không phải tên runner mặc định của một CI provider. Với mỗi job, cần cài/chọn JDK và native toolchain đúng target, sau đó chạy test trong môi trường runtime tương ứng.

Đối với JAR thuần Java, có thể tách pipeline thành:

1. Một job build JAR duy nhất với `--release` đã khóa.
2. Các job test chạy JAR trên từng JDK/OS/CPU được hỗ trợ.
3. Các job package tạo runtime/application image theo từng target nếu cần.

Nếu có native code, thêm job build native riêng cho mỗi target hoặc cấu hình cross-compile được kiểm chứng. Không tái sử dụng binary native của job x64 cho job ARM64.

## 9. Docker Buildx và image đa kiến trúc

Docker Buildx có thể build và publish manifest đa kiến trúc:

```sh
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/team/app:2.4.0 \
  --push .
```

Manifest list cho phép Docker chọn image con phù hợp kiến trúc khi pull. Nó không biến một binary x64 thành ARM64. Mỗi image con vẫn phải chứa JDK/JRE và native dependency đúng kiến trúc.

Nếu dùng `FROM --platform=$BUILDPLATFORM` để build trên máy build khác kiến trúc target, hãy khai báo rõ `TARGETPLATFORM`, target triple và cross toolchain. Việc này có thể phù hợp với compile Java thuần hoặc native project có quy trình cross-compile đầy đủ; nó không tự làm compiler mặc định tạo binary cho target.

Với native library, cách dễ xác minh nhất thường là build trên runner native của từng kiến trúc hoặc dùng cross-compiler cùng sysroot đã khóa, sau đó chạy test trên runtime target. Không nên dựa vào QEMU emulation như bằng chứng duy nhất cho hiệu năng và mọi hành vi native.

## 10. Tạo jlink runtime và jpackage application image trong CI

`jlink` và `jpackage` tạo artifact có launcher/runtime native theo nền tảng. Vì vậy, pipeline nên tạo runtime image và application image trên runner tương ứng với target, hoặc dùng quy trình cross-build được hỗ trợ rõ ràng.

Một job Linux target có thể thực hiện:

```sh
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|os.name|os.arch'

jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging \
  --output runtime

jpackage \
  --type app-image \
  --name ExampleApp \
  --input target \
  --main-jar app.jar \
  --runtime-image runtime
```

Ví dụ chỉ chọn hai module để minh họa; ứng dụng thực tế cần module list đầy đủ, bao gồm các service provider hoặc module được nạp động. Gói kết quả cần được chạy thử bằng chính launcher và runtime trong image.

Nếu build Windows ARM64, macOS ARM64 hoặc Linux musl, hãy dùng JDK/toolchain đúng target. Không lấy runtime image được tạo trên runner Linux x64 glibc rồi copy vào image Alpine ARM64.

## 11. Khóa phiên bản và làm build có thể tái lập

Để pipeline có kết quả ổn định, cần khóa nhiều hơn phiên bản Java:

| Thành phần | Cách quản lý |
|---|---|
| JDK vendor/version | Khóa major, patch release và kiến trúc; theo dõi lịch CPU/security update |
| Build tool | Dùng Maven Wrapper hoặc Gradle Wrapper, khóa wrapper distribution/checksum |
| Java API target | Khai báo `--release` hoặc `options.release` |
| Native compiler | Khóa phiên bản compiler/linker và target triple |
| SDK/sysroot | Khóa Windows SDK, macOS SDK hoặc Linux sysroot/libc target |
| Container base | Dùng tag cụ thể và digest đã xác minh |
| Dependency | Dùng dependency lock/checksum và repository đáng tin cậy |
| Artifact | Ghi target OS/CPU/libc, JDK vendor/version và checksum |

Không dùng tag `latest` cho build production cần tái lập. Pin digest giúp build dùng đúng image đã kiểm thử, nhưng không thay thế quy trình cập nhật: cần định kỳ cập nhật digest khi có bản vá bảo mật và chạy lại test.

Cache CI cũng nên phân biệt theo hệ điều hành, kiến trúc, JDK và native toolchain. Không chia sẻ thư mục output native giữa `linux/amd64` và `linux/arm64`, hoặc giữa glibc và musl. Cache dependency Java thuần có thể dùng chung có kiểm soát, nhưng cache build output cần có khóa target.

## 12. Xác minh môi trường ngay trong pipeline

Mỗi job nên in thông tin runtime và compiler trước khi build:

```sh
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.version|java.vendor|java.home|os.name|os.arch'

cc --version
ld --version
uname -m
```

Lệnh `ld --version` tùy toolchain; trên môi trường musl có thể không có GNU `ld` hoặc output khác. CI nên kiểm tra bằng công cụ có sẵn trong image và không giả định mọi target Linux đều có cùng lệnh. Với Windows, ghi lại `cl`/MSVC version, Windows SDK và kết quả `dumpbin /headers` cho native artifact. Với macOS, ghi lại `clang --version`, `xcodebuild -version` và deployment target.

Sau build, xác minh:

- JAR có class-file version và API phù hợp với runtime tối thiểu.
- Native binary có đúng kiến trúc và ABI/libc.
- Runtime image báo đúng `os.arch` và khởi động được.
- Application image/installer chứa đúng runtime và launcher cho target.
- Integration test chạy trong image cuối cùng, không chỉ trong build stage.
- Artifact có checksum, metadata và provenance gắn với job/commit tạo ra nó.

## 13. Những sai lệch thường gặp trong CI

| Sai lệch | Hậu quả | Cách phòng tránh |
|---|---|---|
| Build dùng JDK mới nhưng không đặt `--release` | Dùng API/class-file mới hơn runtime production | Khóa `--release` và kiểm tra runtime tối thiểu |
| `JAVA_HOME` khác JDK mà PATH chọn | Build/test dùng JDK không như dự kiến | In đường dẫn `java`, `javac`, `java.home` và cấu hình toolchain |
| Compiler native tạo binary theo build host | Binary sai CPU hoặc ABI target | Chọn native runner hoặc cross-compiler/sysroot đúng target |
| Build `.so` glibc rồi copy vào Alpine musl | Lỗi loader, symbol hoặc `UnsatisfiedLinkError` | Build/lấy binary musl hoặc dùng runtime glibc tương thích |
| Dùng JDK x64 trong Windows ARM64 nhưng đóng gói DLL ARM64 | Không thể nạp DLL vào process x64 | Khớp kiến trúc DLL với kiến trúc JVM process |
| Dùng `jlink` runtime từ runner khác target | Runtime image không chạy trên target | Tạo runtime bằng JDK đúng OS/CPU/ABI |
| Cache output dùng chung giữa nhiều target | Lẫn object file hoặc native binary | Thêm OS/arch/libc/toolchain vào cache key |
| Chỉ test trên build image | Bỏ sót thư viện thiếu trong runtime image | Test trong đúng image cuối cùng |
| Pin tag nhưng không cập nhật digest | Giữ lại base/JDK có lỗ hổng đã biết | Theo dõi patch, cập nhật digest và chạy lại pipeline |

## 14. Quy trình mẫu cho một pipeline đa nền tảng

Một quy trình thực tế có thể tổ chức thành các bước:

1. **Đọc target matrix:** xác định OS, CPU, libc/ABI và JDK tối thiểu được hỗ trợ.
2. **Provision build environment:** chọn build JVM, compiler toolchain và native SDK đúng target.
3. **Compile Java:** dùng Maven/Gradle Wrapper, toolchain rõ ràng và `--release` đã khóa.
4. **Build native dependency:** dùng native runner hoặc cross toolchain cùng sysroot đã xác minh.
5. **Package:** tạo JAR dùng chung khi phù hợp; tạo runtime image/application image riêng theo target.
6. **Test:** chạy unit test, integration test và smoke test trong image runtime cuối cùng.
7. **Audit:** kiểm tra kiến trúc binary, libc/ABI, dependency, checksum và lỗ hổng image.
8. **Publish:** đính kèm metadata target, JDK vendor/version, digest và provenance.
9. **Maintain:** theo dõi bản vá JDK, compiler, SDK và base image; cập nhật có kiểm thử.

Không phải mọi job đều cần chạy trên cùng một loại runner. Điều quan trọng là artifact được tạo có target được khai báo, công cụ tương thích và test xác nhận đúng môi trường cuối.

## 15. Ghi nhớ

- Chốt target OS/CPU/libc trước khi chọn JDK và toolchain.
- Phân biệt JDK chạy build tool, compiler toolchain, test runtime và production runtime.
- Dùng `--release` để khóa API/class-file; nó không chọn kiến trúc native.
- Khóa compiler, linker, SDK, sysroot và ABI khi có mã native.
- JAR thuần Java thường có thể dùng chung; native binary, `jlink` runtime và `jpackage` image cần đúng target.
- Giữ build image và runtime image tương thích về JDK, kiến trúc và libc khi build native code.
- Docker multi-arch tạo nhiều image con theo target; nó không chuyển binary giữa kiến trúc.
- Pin version/digest để tái lập, đồng thời có lịch cập nhật bảo mật.
- Test trong image runtime cuối cùng và lưu metadata/checksum của artifact.

CI đáng tin cậy khi mỗi artifact được tạo bằng JDK, native toolchain và image nền đã xác định cho đúng target. Khi các lựa chọn này được khai báo và kiểm tra tự động, lỗi “build được nhưng không chạy được” do lệch kiến trúc hoặc ABI sẽ giảm đáng kể trên các nền tảng Java hiện đại.
