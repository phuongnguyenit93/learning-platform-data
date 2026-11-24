# Multi-stage Dockerfile tách môi trường biên dịch khỏi runtime image

Ứng dụng Spring Boot đã được biên dịch thành **GraalVM Native Image** có thể chạy như một executable Linux độc lập, không cần mang theo JVM. Vì vậy, container production không cần chứa JDK, Maven/Gradle, compiler hay toàn bộ source code. Một **multi-stage Dockerfile** tách giai đoạn build (cần GraalVM Native Image toolchain) khỏi giai đoạn runtime (chỉ cần executable và các thư viện hệ điều hành mà executable liên kết tới).

Trong module **`SPRING_BOOT_NATIVE_IMAGE`**, mục tiêu là biên dịch Spring Boot bằng Spring AOT, đánh giá startup và memory, kiểm thử tương thích, đóng gói container và vận hành bản native. Bài học này hướng dẫn tạo Dockerfile nhiều stage cho Maven và Gradle, tận dụng build cache, chọn runtime image phù hợp với native executable, chạy container bằng user không đặc quyền và kiểm tra các lỗi thường gặp khi chuyển binary từ builder sang runtime.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của builder stage và runtime stage.
- Chọn GraalVM container image có `native-image` tool để build executable.
- Viết multi-stage Dockerfile cho Spring Boot native với Maven hoặc Gradle.
- Tổ chức `COPY` để tận dụng Docker layer cache và `.dockerignore` để thu nhỏ build context.
- Phân biệt native executable liên kết động với executable static.
- Kiểm tra glibc, shared libraries và kiến trúc CPU giữa builder và runtime image.
- Tạo runtime image không chứa JDK, Maven/Gradle và compiler.
- Chạy ứng dụng bằng non-root user, giới hạn quyền ghi và quản lý secret an toàn.
- Xác minh container bằng health endpoint và kiểm tra log.

## 2. Vì sao cần multi-stage build?

Một build Native Image cần nhiều công cụ:

- JDK/GraalVM và tiện ích `native-image`.
- Native compiler, linker và các thư viện phát triển C/C++.
- Maven hoặc Gradle cùng dependency cache.
- Source code, generated AOT sources và reachability metadata.

Các thành phần này chỉ cần trong lúc build. Runtime image thường chỉ cần:

- Executable được tạo ra.
- Các shared libraries mà executable phụ thuộc (nếu binary liên kết động).
- CA certificates, timezone data hoặc file hệ thống khác nếu ứng dụng cần.
- Thư mục tạm và cấu hình runtime.

Docker multi-stage build dùng nhiều lệnh `FROM`. Mỗi stage có filesystem riêng; stage cuối cùng xác định nội dung image được phát hành. Ta dùng `COPY --from=<stage>` để lấy đúng executable từ builder stage sang runtime stage. Các layer chứa compiler và source trong builder không được đưa vào image cuối nếu không copy chúng.

~~~mermaid
flowchart TD
    A["Source + Maven/Gradle project"] --> B["Builder stage: GraalVM + native-image"]
    B --> C["Spring AOT processing"]
    C --> D["Native Image compiler"]
    D --> E["Executable Linux"]
    E --> F["COPY --from=builder"]
    F --> G["Runtime stage: OS libraries + executable"]
    G --> H["Non-root container"]
~~~

Lợi ích:

1. **Runtime image nhỏ hơn:** không chứa compiler, JDK, build tool và source.
2. **Giảm attack surface:** giảm số package và công cụ có thể bị khai thác trong production.
3. **Tách trách nhiệm:** builder có toolchain đầy đủ; runtime chỉ có thứ ứng dụng cần.
4. **Build nhanh hơn khi có cache:** dependency layers có thể được tái sử dụng khi chỉ source code thay đổi.
5. **Dễ kiểm soát runtime:** có thể chọn base image, user, thư mục ghi và shared libraries riêng.

Multi-stage build không tự động làm executable thành static. Native Image mặc định thường vẫn liên kết động với một số thư viện hệ điều hành; runtime image phải cung cấp các thư viện đó.

## 3. Chọn builder image

GraalVM Community Edition cung cấp container image `native-image-community` trên GitHub Container Registry. Image này có GraalVM JDK và tiện ích `native-image`; tag có thể chọn theo Java feature version, GraalVM release và Oracle Linux platform.

Ví dụ builder cho Java 21:

~~~dockerfile
FROM ghcr.io/graalvm/native-image-community:21-ol9 AS builder
~~~

Tag trên là ví dụ. Hãy chọn GraalVM/JDK tương thích với Java target, Spring Boot, Native Build Tools và dependency của dự án. Trong CI production, nên pin tag cụ thể hơn hoặc image digest để build có thể tái lập và tránh việc tag ít cụ thể trỏ sang image mới sau này.

Kiểm tra image trước khi dùng:

~~~bash
docker run --rm ghcr.io/graalvm/native-image-community:21-ol9 java -version
docker run --rm ghcr.io/graalvm/native-image-community:21-ol9 native-image --version
~~~

Nếu dự án dùng Java 17 hoặc 25, chọn image GraalVM tương ứng thay vì giữ nguyên tag Java 21. Không lấy JDK runtime image thông thường làm builder nếu image đó không có `native-image` và toolchain cần thiết.

## 4. Dockerfile Maven: build native trong builder stage

Ví dụ dưới đây giả định:

- Maven Wrapper nằm ở root: `mvnw`, `.mvn/`.
- Spring Boot Maven plugin và GraalVM Native Build Tools đã được cấu hình.
- Profile `native` chạy Spring AOT và native compile.
- Maven `artifactId` là `orders-service`, nên executable được tạo ở `target/orders-service`.

~~~dockerfile
# syntax=docker/dockerfile:1

ARG GRAALVM_IMAGE=ghcr.io/graalvm/native-image-community:21-ol9
ARG RUNTIME_IMAGE=oraclelinux:9-slim

FROM ${GRAALVM_IMAGE} AS builder

WORKDIR /workspace

# Copy Maven Wrapper và POM trước để dependency layer có thể được cache.
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

RUN chmod +x mvnw

RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -Pnative dependency:go-offline

# Source thay đổi thường xuyên nên được copy sau dependency layer.
COPY src/ src/

RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -Pnative native:compile

# Kiểm tra các shared libraries mà executable liên kết tới.
RUN ldd /workspace/target/orders-service

FROM ${RUNTIME_IMAGE} AS runtime

WORKDIR /app

COPY --from=builder --chown=10001:10001 --chmod=0555 \
    /workspace/target/orders-service /app/orders-service

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/orders-service"]
~~~

### Giải thích các stage

**Builder stage**

- `GRAALVM_IMAGE` chứa GraalVM và Native Image toolchain.
- `.mvn`, `mvnw` và `pom.xml` được copy trước source để thay đổi code không làm mất cache dependency.
- `dependency:go-offline` tải dependency và plugin cần thiết theo profile `native`.
- `native:compile` thực hiện quy trình native build đã cấu hình trong Maven project, bao gồm Spring AOT processing theo cấu hình Spring Boot.
- `ldd` hiển thị các thư viện động mà executable yêu cầu. Hãy đọc output để xác định runtime image cần cung cấp gì.

**Runtime stage**

- Bắt đầu từ Oracle Linux slim cùng major version với builder để giảm rủi ro khác biệt ABI/glibc.
- Chỉ copy executable từ builder; không copy JDK, Maven, source hoặc thư mục `target` đầy đủ.
- `--chmod=0555` đặt executable permission chỉ đọc/chạy.
- `--chown=10001:10001` gán file cho UID/GID không đặc quyền.
- `USER` bảo đảm tiến trình không chạy bằng root.

Nếu `artifactId`, tên executable hoặc output directory của Maven project khác ví dụ, hãy sửa đúng đường dẫn ở lệnh `ldd` và `COPY --from=builder`. Với multi-module Maven, cần copy parent POM, POM của các module liên quan và source theo cấu trúc thực tế; không thể chỉ copy một `pom.xml` ở root nếu module build phụ thuộc các POM khác.

### Build và chạy image

Từ thư mục chứa Dockerfile:

~~~bash
docker build --pull \
  --build-arg GRAALVM_IMAGE=ghcr.io/graalvm/native-image-community:21-ol9 \
  --build-arg RUNTIME_IMAGE=oraclelinux:9-slim \
  -t orders-service:native .
~~~

Chạy container:

~~~bash
docker run --rm -p 8080:8080 orders-service:native
~~~

Từ host, gọi endpoint của ứng dụng, ví dụ:

~~~bash
curl http://localhost:8080/actuator/health
~~~

Endpoint này cần được bật và cho phép truy cập theo cấu hình Spring Boot Security của dự án. Nếu ứng dụng không có Actuator, hãy gọi endpoint readiness/health do ứng dụng cung cấp.

## 5. Tối ưu Docker cache và build context

Docker xây dựng image theo layer. Khi một layer thay đổi, các layer phía sau có thể phải chạy lại. Vì vậy, nên copy các file ít thay đổi (wrapper, POM, build scripts) trước source code.

Ví dụ `.dockerignore`:

~~~text
.git
.idea
.vscode
.gradle
build
target
*.log
.env
.env.*
~~~

Không loại `.mvn/`, `gradle/`, Maven/Gradle wrapper hoặc file build cần thiết. Nếu project có generated sources, schema, frontend assets hoặc file cấu hình build riêng, hãy giữ chúng trong context và copy đúng stage.

### BuildKit cache mount

Lệnh Maven dùng:

~~~dockerfile
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -Pnative dependency:go-offline
~~~

Cache mount lưu Maven repository giữa các lần build trên builder hỗ trợ BuildKit. Cache này không trở thành một phần của runtime image.

Nếu dùng private Maven repository, không copy `settings.xml` chứa token vào image và không truyền password qua `ARG` hoặc `ENV`. Dùng BuildKit secret mount:

~~~dockerfile
RUN --mount=type=secret,id=maven-settings,target=/root/.m2/settings.xml \
    --mount=type=cache,target=/root/.m2/repository \
    ./mvnw -B -ntp -Pnative native:compile
~~~

Build với secret:

~~~bash
docker build \
  --secret id=maven-settings,src=./settings.xml \
  -t orders-service:native .
~~~

Chỉ dùng secret mount khi thực sự cần truy cập repository riêng. Không đưa file settings có credential vào build context nếu `.dockerignore` chưa loại nó.

## 6. Biến thể Gradle Native Build Tools

Với Gradle, builder stage dùng cùng GraalVM Native Image image, nhưng gọi Gradle Wrapper và task `nativeCompile`. Plugin `org.graalvm.buildtools.native` phải được áp dụng trong build; Spring Boot Gradle plugin sẽ phối hợp AOT tasks theo cấu hình.

Ví dụ cấu hình tên executable trong `build.gradle`:

~~~groovy
graalvmNative {
    binaries {
        main {
            imageName = "orders-service"
        }
    }
}
~~~

Dockerfile Gradle:

~~~dockerfile
# syntax=docker/dockerfile:1

ARG GRAALVM_IMAGE=ghcr.io/graalvm/native-image-community:21-ol9
ARG RUNTIME_IMAGE=oraclelinux:9-slim

FROM ${GRAALVM_IMAGE} AS builder

WORKDIR /workspace

COPY gradlew settings.gradle build.gradle ./
COPY gradle/ gradle/

RUN chmod +x gradlew

# Nếu project dùng Kotlin DSL, version catalog, gradle.properties,
# buildSrc hoặc included build, copy các file đó ở layer này.
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon help

COPY src/ src/

RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon nativeCompile

RUN ldd /workspace/build/native/nativeCompile/orders-service

FROM ${RUNTIME_IMAGE} AS runtime

WORKDIR /app

COPY --from=builder --chown=10001:10001 --chmod=0555 \
    /workspace/build/native/nativeCompile/orders-service /app/orders-service

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/orders-service"]
~~~

Đường dẫn output ở trên là đường dẫn mặc định thường dùng của Gradle Native Build Tools. Nếu đã cấu hình `buildDirectory`, binary name hoặc native binary khác, hãy kiểm tra output của task `nativeCompile` rồi cập nhật đường dẫn. Với Kotlin DSL hoặc multi-project build, copy thêm `settings.gradle.kts`, `build.gradle.kts`, `gradle.properties`, `gradle/libs.versions.toml`, `buildSrc` và các subproject cần thiết trước khi chạy Gradle.

Build:

~~~bash
docker build -t orders-service:native .
~~~

Cache mount `/root/.gradle` giúp giữ Gradle distribution và dependency cache giữa các lần build. Đừng copy toàn bộ thư mục `.gradle` từ máy phát triển vào runtime image.

## 7. Chọn runtime image và kiểm tra shared libraries

Native executable là binary Linux theo kiến trúc CPU và môi trường ABI mà nó được build. Runtime image phải cung cấp các shared libraries cần thiết.

### 7.1. Giữ cùng hệ điều hành nền khi mới bắt đầu

Ví dụ Dockerfile dùng GraalVM builder dựa trên Oracle Linux 9 và runtime `oraclelinux:9-slim`. Cùng major version giúp giảm khả năng executable yêu cầu symbol glibc mới hơn runtime image.

Không nên build trên một distro mới rồi chạy trên distro cũ hơn mà chưa kiểm tra glibc compatibility. Executable được build với glibc mới có thể tham chiếu symbol mà runtime glibc cũ không có.

### 7.2. Đọc output ldd

Trong builder stage:

~~~bash
ldd target/orders-service
~~~

Output hiển thị các shared library và đường dẫn tìm thấy trong builder. Nếu có `not found`, cần xác định dependency còn thiếu. Kể cả khi mọi thư viện có mặt trong builder, runtime image vẫn cần chứa các thư viện tương ứng.

Các dependency có thể gặp gồm:

- glibc và các thư viện hệ thống cơ bản.
- libstdc++ hoặc libgcc nếu binary liên kết tới chúng.
- zlib hoặc thư viện TLS/crypto tùy build và dependency.
- CA certificates khi ứng dụng gọi HTTPS.
- timezone data nếu ứng dụng cần timezone database của hệ điều hành.

Không cài compiler hoặc toàn bộ build toolchain vào runtime chỉ để giải quyết một shared library bị thiếu. Hãy xác định chính xác package runtime cần thiết và chỉ thêm package đó vào runtime stage.

### 7.3. Dùng Distroless làm runtime stage

Khi đã biết chính xác shared libraries mà binary cần, có thể thay runtime stage bằng image tối giản như:

~~~dockerfile
FROM gcr.io/distroless/base-debian13:nonroot AS runtime
WORKDIR /app
COPY --from=builder --chown=nonroot:nonroot --chmod=0555 \
    /workspace/target/orders-service /app/orders-service
EXPOSE 8080
ENTRYPOINT ["/app/orders-service"]
~~~

Distroless base image có glibc và một số thư viện hệ thống phổ biến nhưng không chứa shell hoặc package manager. Phải xác minh binary tương thích ABI và tất cả thư viện cần thiết có trong image. Nếu thiếu thư viện C++ hoặc thư viện khác, chọn biến thể phù hợp hoặc runtime image khác; không giả định mọi Native Image đều chạy được trên `static` image.

Distroless `static` dành cho executable không cần glibc. Chỉ dùng khi binary thực sự được build static (ví dụ toolchain musl phù hợp), đã xác minh dependency và đã kiểm thử CA certificates, timezone, `/tmp` cùng các file hệ thống ứng dụng cần.

### 7.4. Build static với musl

GraalVM có biến thể Native Image builder tích hợp musl toolchain, ví dụ tag có hậu tố `muslib`. Cách này có thể tạo executable liên kết static, giúp runtime image nhỏ hơn. Tuy nhiên, cần kiểm tra giới hạn kiến trúc, tính tương thích thư viện native và kết quả build của dự án. Một số image `muslib` chỉ được phát hành cho x86_64; kiểm tra ma trận platform hiện hành trước khi chọn.

Không đổi sang musl chỉ để giảm kích thước image nếu ứng dụng có JNI/native dependencies chưa hỗ trợ musl. Hãy build và chạy integration test trên đúng loại runtime trước khi phát hành.

## 8. Kiến trúc CPU và tính tương thích binary

Native executable phụ thuộc kiến trúc CPU mục tiêu, ví dụ `linux/amd64` hoặc `linux/arm64`. Builder và runtime image phải cùng kiến trúc với binary.

Các image GraalVM Community hiện có multi-architecture variants cho x64 và AArch64, nhưng việc kéo đúng base image chưa đủ để bảo đảm cross-build native image thành công.

Quy tắc an toàn:

- Build executable trên runner/builder có kiến trúc trùng với kiến trúc phát hành.
- Tạo artifact riêng cho amd64 và arm64.
- Không copy binary arm64 vào runtime image amd64 hoặc ngược lại.
- Nếu dùng Docker Buildx/QEMU để giả lập kiến trúc, xác minh GraalVM Native Image có hỗ trợ workflow đó; native compilation có thể rất chậm hoặc gặp giới hạn khi chạy dưới emulation.
- Không dùng `FROM --platform=$BUILDPLATFORM` một cách máy móc cho builder native nếu binary đầu ra cần chạy trên `$TARGETPLATFORM`.

Ví dụ build một image cho amd64 trên runner amd64:

~~~bash
docker buildx build --platform linux/amd64 --load \
  -t orders-service:native-amd64 .
~~~

Với arm64, ưu tiên runner arm64:

~~~bash
docker buildx build --platform linux/arm64 --load \
  -t orders-service:native-arm64 .
~~~

Nếu publish multi-arch manifest, mỗi platform cần binary được build và kiểm thử đúng kiến trúc trước khi ghép manifest.

## 9. Bảo mật runtime container

Multi-stage build giảm công cụ trong runtime, nhưng vẫn cần cấu hình quyền của container.

### 9.1. Chạy non-root

Ví dụ runtime stage đã dùng:

~~~dockerfile
COPY --from=builder --chown=10001:10001 --chmod=0555 \
    /workspace/target/orders-service /app/orders-service
USER 10001:10001
~~~

Ứng dụng nên ghi log ra stdout/stderr. Nếu cần ghi file, mount volume hoặc chỉ định thư mục writable rõ ràng và cấp quyền tối thiểu cho UID chạy ứng dụng.

### 9.2. Read-only filesystem

Có thể chạy container với root filesystem chỉ đọc:

~~~bash
docker run --rm -p 8080:8080 \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  orders-service:native
~~~

Điều chỉnh kích thước `/tmp` và các writable mount theo nhu cầu upload, file tạm hoặc thư viện ứng dụng. Nếu ứng dụng ghi vào thư mục khác, hãy cấp mount cụ thể thay vì mở quyền ghi toàn bộ root filesystem.

### 9.3. Secret và cấu hình runtime

Không đóng gói database password, JWT signing secret, OAuth client secret hoặc private key vào Dockerfile, build argument hay image layer. Truyền chúng qua secret manager hoặc cơ chế secret của nền tảng container.

Có thể truyền property runtime bằng environment:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_DATASOURCE_URL="$SPRING_DATASOURCE_URL" \
  -e SPRING_DATASOURCE_USERNAME="$SPRING_DATASOURCE_USERNAME" \
  orders-service:native
~~~

Ví dụ trên giả định biến môi trường được cấp từ secret/config store của môi trường triển khai. Không ghi credential thật vào shell history hoặc file compose được commit.

## 10. Port, readiness và health check

`EXPOSE 8080` trong Dockerfile chỉ mô tả port mà container dự kiến lắng nghe; nó không tự publish port ra host. Khi chạy local cần map:

~~~bash
docker run --rm -p 8080:8080 orders-service:native
~~~

Ứng dụng Spring Boot mặc định thường lắng nghe port 8080. Có thể cấu hình port runtime bằng `SERVER_PORT` hoặc `server.port`, nhưng phải bảo đảm port mapping và probe trùng với port thực tế.

Nếu có Spring Boot Actuator, bật endpoint health/readiness theo nhu cầu triển khai. Kubernetes có thể dùng readiness probe để chỉ gửi traffic sau khi ứng dụng sẵn sàng; liveness probe dùng để phát hiện process bị treo theo chính sách phù hợp.

Không thêm `HEALTHCHECK` gọi `curl` vào runtime image tối giản nếu image không có shell/curl. Hãy dùng probe từ orchestrator hoặc chọn một health-check binary được quản lý rõ ràng. Với Distroless, không có shell để debug trực tiếp; có thể dùng image `debug` tạm thời trong môi trường chẩn đoán, không phát hành debug image như runtime mặc định.

## 11. Buildpacks và Dockerfile thủ công

Spring Boot hỗ trợ Cloud Native Buildpacks với Paketo Java Native Image buildpack. Với Maven, project đã cấu hình native profile có thể dùng:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Với Gradle:

~~~bash
./gradlew bootBuildImage
~~~

Khi Native Image plugin đã được cấu hình, Spring Boot có thể tạo image chứa native executable bằng Buildpacks. Đây là lựa chọn tiện lợi khi muốn để buildpack quản lý builder/runtime image.

Multi-stage Dockerfile thủ công phù hợp khi cần:

- Kiểm soát builder image, runtime base image và OS baseline.
- Kiểm soát chính xác file nào được đưa vào runtime.
- Áp dụng quy ước image, security policy và build cache riêng của tổ chức.
- Tùy chỉnh runtime user, writable paths và cách đóng gói.

Hai phương pháp đều có thể tạo container chạy native executable. Hãy chọn một quy trình nhất quán cho CI/CD và ghi lại version/tag của builder image.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `native-image: command not found` | Builder image không có Native Image tool hoặc tag sai | Dùng `native-image-community` và kiểm tra version |
| Maven không tìm thấy profile `native` | POM chưa cấu hình profile/plugin như hướng dẫn Spring Boot | Kiểm tra Maven plugin và native profile |
| Không tìm thấy `target/orders-service` | Tên executable hoặc output path khác | Kiểm tra `artifactId`, `imageName` và output native compile |
| `exec format error` | Binary khác kiến trúc CPU với runtime | Build lại trên đúng target architecture |
| `error while loading shared libraries` | Runtime image thiếu thư viện động | Đọc `ldd`, cài đúng runtime package hoặc chọn base tương thích |
| `GLIBC_x.y not found` | Binary cần glibc mới hơn runtime | Dùng runtime cùng/mới hơn baseline builder hoặc rebuild trên baseline thấp hơn |
| Container thoát ngay sau start | Executable lỗi, cấu hình thiếu hoặc app shutdown | Xem `docker logs`, chạy binary trong runtime stage để chẩn đoán |
| Không ghi được file tạm | Root filesystem read-only hoặc `/tmp` không writable | Mount tmpfs/volume và cấp quyền cho non-root UID |
| Container không truy cập HTTPS | Thiếu CA certificates hoặc trust store | Thêm CA bundle phù hợp và kiểm tra TLS |
| Chạy được trên host nhưng lỗi trong container | Host có thư viện mà runtime image không có | Kiểm tra `ldd` và test trên đúng final image |
| Image cuối vẫn rất lớn | Copy cả JDK, source hoặc build directory | Chỉ `COPY --from=builder` executable và file runtime cần thiết |
| Build luôn tải lại dependencies | Layer order chưa tối ưu hoặc cache mount chưa dùng | Copy build files trước source và dùng BuildKit cache |

## 13. Checklist trước khi phát hành

- [ ] Chọn GraalVM builder image đúng Java feature version và Native Image tool.
- [ ] Pin builder/runtime image tag hoặc digest theo chính sách CI.
- [ ] Chạy Spring AOT và native compile thành công trong builder stage.
- [ ] Xác định chính xác tên và đường dẫn executable.
- [ ] Kiểm tra output `ldd` hoặc công cụ tương đương cho shared libraries.
- [ ] Chọn runtime image có ABI và thư viện tương thích.
- [ ] Chỉ copy executable và runtime assets cần thiết sang final stage.
- [ ] Dùng `.dockerignore` để loại build output, IDE files và secret.
- [ ] Dùng BuildKit cache cho Maven/Gradle dependency repository.
- [ ] Không lưu secret trong `ARG`, `ENV`, Dockerfile hoặc image layer.
- [ ] Chạy container bằng non-root user.
- [ ] Xác định các thư mục cần writable và cấu hình volume/tmpfs tối thiểu.
- [ ] Kiểm tra port, readiness, health endpoint và log.
- [ ] Build/test riêng cho từng kiến trúc CPU phát hành.
- [ ] Scan image, kiểm tra SBOM và lưu digest của image đã phát hành.

## 14. Bài tập tự kiểm tra

**Câu 1.** Vì sao builder stage cần GraalVM Native Image nhưng runtime stage không cần JDK?

**Gợi ý:** builder biên dịch code thành executable; native executable không cần JVM để khởi chạy.

**Câu 2.** Vì sao không thể mặc định dùng `scratch` hoặc Distroless `static` cho mọi native executable?

**Gợi ý:** binary mặc định có thể liên kết động với glibc, zlib hoặc thư viện hệ thống khác; runtime phải cung cấp dependency đó.

**Câu 3.** Vì sao nên copy POM/build scripts trước source code?

**Gợi ý:** dependency layer ít thay đổi hơn source, nên Docker có thể tái sử dụng cache khi code thay đổi.

**Câu 4.** `COPY --from=builder` có tác dụng gì?

**Gợi ý:** lấy artifact từ builder stage sang runtime stage mà không đưa toàn bộ filesystem builder vào image cuối.

**Câu 5.** `EXPOSE 8080` có tự publish port ra host không?

**Gợi ý:** không. Cần `-p hostPort:containerPort` khi chạy Docker hoặc cấu hình port/service trong orchestrator.

**Câu 6.** Vì sao binary chạy được trên máy build nhưng lỗi `GLIBC_x.y not found` trong container?

**Gợi ý:** runtime image có glibc cũ hơn symbol version mà binary yêu cầu.

**Câu 7.** Nếu muốn hỗ trợ cả amd64 và arm64, có thể dùng một binary native duy nhất không?

**Gợi ý:** không. Native executable được biên dịch theo kiến trúc; cần build và kiểm thử artifact riêng cho mỗi platform.

## 15. Tài liệu tham khảo

- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/): nhiều build stage và copy artifact sang stage cuối.
- [Docker — Build cache optimization](https://docs.docker.com/build/cache/optimize/): thứ tự layer, build context và cache mount.
- [Docker — Build best practices](https://docs.docker.com/build/building/best-practices/): `.dockerignore`, pin image và multi-stage build.
- [GraalVM — Community Edition Container Images](https://www.graalvm.org/latest/getting-started/container-images/): image `native-image-community`, tag, Java version, Oracle Linux và architecture.
- [Spring Boot — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): native executable và lựa chọn Buildpacks/Maven/Gradle.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): khác biệt giữa JVM và Native Image, closed-world và AOT.
- [Google Distroless — Base images](https://github.com/GoogleContainerTools/distroless/blob/main/base/README.md): nội dung runtime base, glibc và các biến thể distroless.

**Ghi nhớ:** Multi-stage Dockerfile đưa GraalVM compiler và build tools vào builder stage, sau đó chỉ chuyển native executable cùng runtime dependencies sang final stage. Hãy kiểm tra shared libraries, glibc baseline và kiến trúc CPU trước khi chọn runtime image; chạy non-root, quản lý secret ngoài image và xác minh chính final container bằng health/readiness test.
