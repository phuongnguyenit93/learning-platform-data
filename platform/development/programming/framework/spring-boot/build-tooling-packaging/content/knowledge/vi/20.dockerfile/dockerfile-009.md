# Quản lý base image theo tag, digest và kiến trúc CPU trong Dockerfile cho Spring Boot

## 1. Mục tiêu: chọn đúng nền tảng, tái lập được và cập nhật bảo mật

Một Spring Boot executable JAR có thể chạy trên nhiều CPU architecture nếu mã và dependencies tương thích, nhưng **container image không tự động đa kiến trúc**. Image base chứa hệ điều hành tối giản, Java runtime và có thể có thư viện native, vì vậy phụ thuộc vào **OS/CPU architecture** và phiên bản cụ thể của base image.

Một Dockerfile rất quen thuộc:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/base-demo-0.1.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

đã đặt ra ba lựa chọn vận hành:

1. **Tag** `17-jre`: tên thuận tiện cho người đọc nhưng publisher có thể cập nhật nội dung phía sau tag.
2. **Digest** `sha256:...`: địa chỉ theo nội dung, xác định manifest/index cụ thể, giúp kiểm toán và pin base image.
3. **Platform** `linux/amd64`, `linux/arm64`...: xác định image variant tương thích CPU/kernel/runtime cần triển khai.

Nếu developer dùng laptop ARM64 còn máy chủ production là AMD64, Docker có thể chọn **hai biến thể khác nhau** của cùng một tag multi-platform. Nếu CI build lại sau vài tháng, tag có thể trỏ tới **bản vá JRE/OS mới**. Hành vi đó có thể tốt về bảo mật nhưng không đồng nghĩa bản dựng byte-for-byte tái lập.

**Kết quả cần đạt sau bài học:**
- Hiểu tag, digest, manifest, manifest list/OCI index và platform là các khái niệm khác nhau.
- Kiểm tra image reference và các kiến trúc được publisher phát hành bằng Docker Buildx.
- Chọn cách pin image bằng digest mà không giả mạo một giá trị SHA-256.
- Tạo Spring Boot Java 17 JAR và Dockerfile chạy được trên `linux/amd64`/`linux/arm64` khi base hỗ trợ.
- Build/push một multi-platform image có kiểm thử và lựa chọn artifact phù hợp khi triển khai.
- Cân bằng **tính ổn định – cập nhật lỗ hổng – tốc độ CI – khả năng hỗ trợ CPU**.

Ví dụ sử dụng Spring Boot **3.5.0**, Java 17 và Docker Buildx/BuildKit để có tài liệu tự nhất quán; đây không phải khẳng định về các phiên bản mới nhất. Giá trị digest thực tế phải lấy trực tiếp từ **registry tại thời điểm pin**, không được tự bịa hoặc lấy từ bài viết cũ.

## 2. Ba định danh của base image: repository, tag và digest

Docker/OCI reference điển hình:

```text
docker.io/library/eclipse-temurin:17-jre

registry/repository              tag
          \                       /
     eclipse-temurin           17-jre
                 \              /
          eclipse-temurin:17-jre

eclipse-temurin:17-jre@sha256:<64 hex characters>
                  \            /
                tag         pinned digest
```

`<64 hex characters>` trong sơ đồ là **ký hiệu mô tả định dạng**, không phải digest thực và không phải lệnh Docker chạy được.

| Thành phần | Ý nghĩa | Có thể thay đổi theo thời gian? |
| --- | --- | --- |
| Registry host | Nơi phân phối image, ví dụ Docker Hub hoặc registry doanh nghiệp | Có thể migrate/đổi quyền |
| Repository | Namespace/tên image, ví dụ `eclipse-temurin` | Tên logic ổn định theo publisher |
| Tag | Alias dễ đọc, ví dụ `17-jre`, `17-jre-jammy`, `0.1.0` | **Có thể mutable**: tag có thể được gán manifest/index mới |
| Digest | Hash của đối tượng manifest/index được tham chiếu | Bytes đã hash là cố định; registry có thể ngừng giữ/phục vụ đối tượng |
| Platform | OS/architecture[/variant] dùng để chọn executable/container layers | Không phải version, không thay thế digest |

### 2.1. Tag chỉ là tên, không phải cam kết immutable

`FROM eclipse-temurin:17-jre` có nghĩa “dùng image được registry trả về cho tag `17-jre`”. Nhà phát hành có thể cập nhật tag này để vá CVE, cập nhật Java 17 patch hoặc thay OS package, tùy chính sách phát hành.

Ngay cả tag trông rất cụ thể như `17.0.x_yy-jre` vẫn **không mặc nhiên bất biến** trừ khi registry/publisher cam kết và thực thi quy tắc immutable tags. Nhiều registry riêng hỗ trợ tag immutability policy; đó là chính sách registry, không phải tính chất chung của cú pháp tag.

**Rủi ro:** cùng một Dockerfile, cùng Git commit, nhưng build ở hai thời điểm có thể kéo hai base image khác nhau. Không nên coi `:latest` là chiến lược reproducibility; thực chất lược bỏ tag thường được hiểu là dùng `latest`.

### 2.2. Digest tham chiếu chính xác một manifest hoặc index

Cú pháp:

```text
eclipse-temurin@sha256:<64-hex>
eclipse-temurin:17-jre@sha256:<64-hex>
```

Khi reference có cả tag và digest, **digest xác định đối tượng được lấy**; tag là ngữ cảnh dễ đọc, không khiến builder bỏ qua digest rồi lấy tag mới. Docker docs mô tả pin bằng `image:tag@sha256:...` để tránh tag cập nhật ngoài dự kiến.

**Không nhầm** digest của manifest/index với:
- `docker image inspect .Id`, thường là digest của **image config**;
- SHA-256 của một compressed layer;
- SHA-256 của executable `app.jar`;
- Git commit hash hay tên version trong tag;
- `RepoDigests` sau pull, vì giá trị/loại digest nhìn thấy có thể phụ thuộc registry và image store.

Chúng là các hash của **đối tượng khác nhau**. Muốn pin FROM, cần một **digest reference mà registry phục vụ**, không lấy một hash JAR rồi ghép vào `FROM`.

### 2.3. Ưu điểm và giá phải trả khi pin

**Ưu điểm:** độ ổn định dependency nền, dễ truy vết CVE/rollbacks, audit dùng chính xác base version nào, tránh thay đổi ngầm từ publisher.

**Chi phí:** pin lâu mà không cập nhật sẽ **không nhận tự động các bản vá bảo mật**. Một digest có thể bị registry xóa theo retention policy, khiến rebuild trong tương lai không pull được dù source còn nguyên. Vì vậy pin phải đi với **quy trình cập nhật digest theo lịch hoặc theo cảnh báo**, scan/test, change review và provenance.

## 3. CPU architecture là gì và khác Java bytecode ra sao?

Docker platform thường có dạng:

```text
os/architecture[/variant]

linux/amd64
linux/arm64
linux/arm/v7
windows/amd64
```

Trong ngữ cảnh Linux containers:
- `amd64`: kiến trúc x86-64, thường được `uname -m` báo là `x86_64`.
- `arm64`: 64-bit ARM/AArch64, thường `uname -m` báo `aarch64`.
- `arm/v7`: kiến trúc ARM 32-bit với variant cụ thể; không thể coi tương đương arm64.
- `windows/amd64` là Windows container platform, **không** phải `linux/amd64`.

Một file `.class` biên dịch Java 17 thường có cùng định dạng bytecode trên AMD64 và ARM64. Nhưng JVM binary, libc, thư viện JNI/JNA, native-image, native executables hoặc shell utilities trong base image là **platform-dependent**.

```text
Spring Boot bytecode .jar
          |
          +--> JRE Linux AMD64 + amd64 native libs --> linux/amd64 image
          |
          +--> JRE Linux ARM64 + arm64 native libs --> linux/arm64 image
```

**Kết luận:** “Java write once, run anywhere” không khiến một OCI image single-architecture tự chạy native trên mọi kiến trúc. Cần base variant cho đúng platform, và tất cả thành phần native/OS phải phù hợp.

### 3.1. Không chỉ CPU: OS và ABI cũng quan trọng

Hai base đều `linux/amd64` nhưng có thể khác:
- distro `Ubuntu/Debian` so với `Alpine Linux`;
- `glibc` so với `musl`;
- package manager `apt` so với `apk`;
- CA certificates, locale/tzdata, shell, fonts, openssl native libraries;
- non-root user/permissions và chính sách cập nhật image.

Đừng đổi `eclipse-temurin:17-jre` sang biến thể Alpine/distroless chỉ vì image nhẹ hơn mà chưa kiểm tra JNI/native dependency và hành vi runtime. Java version tương thích **không bảo đảm ABI native tương thích**.

## 4. Multi-platform image: một tag, nhiều manifests

Một multi-platform image reference thường trỏ tới **OCI image index** hoặc **Docker manifest list**:

```text
eclipse-temurin:17-jre  (tag)
           |
           v
OCI index / manifest list  ---> index digest sha256:INDEX...
           |
           +--> linux/amd64 manifest ---> amd64 config + amd64 layers
           |
           +--> linux/arm64 manifest ---> arm64 config + arm64 layers
           |
           +--> platform khác, nếu publisher có phát hành
```

Trong hình, `INDEX...` là mô tả, không phải hash thật. Khi pull/run từ tag/index, Docker thường chọn child manifest tương ứng platform mục tiêu (ví dụ native architecture của host Linux container). Người dùng có thể chỉ rõ platform bằng `docker pull --platform`, `docker run --platform` hoặc `docker buildx build --platform`.

### 4.1. Digest của index khác digest của child manifest

| Loại digest | Đối tượng định danh | Hệ quả khi sử dụng |
| --- | --- | --- |
| **Index digest** | Danh sách các platform variants và những manifest được tham chiếu | Pin **tập platform variants cụ thể**; builder chọn biến thể phù hợp trong tập đó |
| **Platform manifest digest** | Một image variant cụ thể, ví dụ `linux/amd64` | Pin **một** platform; không có sẵn mọi platform khác |
| **Config digest** | JSON cấu hình image variant | Không thay thế reference manifest/index trong `FROM` |
| **Layer digest** | Một lớp filesystem đã nén | Không mô tả toàn bộ base image |

Nếu mục tiêu là build cùng Dockerfile cho cả AMD64 và ARM64, **index digest** thường phù hợp hơn child manifest digest, *với điều kiện index thực sự chứa cả hai platforms*. Pin child digest `linux/amd64` rồi yêu cầu build `linux/arm64` có thể tạo lỗi platform mismatch, pull failure hoặc thành phần runtime không chạy.

**Đừng giả định pin index digest biến mọi kiến trúc thành cùng binary.** AMD64 và ARM64 vẫn có manifests/config/layers riêng; index digest chỉ cố định **danh sách và tham chiếu** tới chúng.

### 4.2. Tình huống không có biến thể phù hợp

Nếu publisher chỉ cung cấp `linux/amd64` nhưng CI yêu cầu `linux/arm64`:
- builder có thể báo **no match for platform in manifest**;
- một số workflow cố chạy binary AMD64 trên ARM có thể cần emulator QEMU;
- nếu binary được chạy native trên host không tương thích, có thể gặp `exec format error`.

Không có cờ Dockerfile nào tự chuyển JRE AMD64 thành ARM64. Cần chọn image có ARM64 variant hoặc tự build/distribute base đúng CPU architecture với kiểm soát thích hợp.

## 5. Kiểm tra base image trước khi dùng

### 5.1. Liệt kê manifest/index trong registry

Docker Buildx:

```bash
docker buildx imagetools inspect eclipse-temurin:17-jre
```

Công cụ đọc thông tin image reference từ registry. Với multi-platform image, output thường có:

```text
Name:       docker.io/library/eclipse-temurin:17-jre
MediaType:  ...
Digest:     sha256:...
Manifests:
  Name:     ...@sha256:...
  Platform: linux/amd64
  Name:     ...@sha256:...
  Platform: linux/arm64
```

Đây là **minh họa cấu trúc output**, không phải digest thực, không cam kết tag luôn có đúng những biến thể/format trình bày đó. Cần đọc các platforms thực tế từ registry tại thời điểm thực hiện.

Lệnh xem JSON manifest gốc:

```bash
docker buildx imagetools inspect --raw eclipse-temurin:17-jre
```

Khi reference trỏ index/list, JSON có `manifests[]` và mỗi phần tử thường có `digest`, `platform.os`, `platform.architecture`, có thể thêm `variant`. **Không nhầm** một số bản phát hành có additional attestation manifests `unknown/unknown` là một CPU architecture có thể chạy ứng dụng.

Nếu đã cài `jq` trên Linux/macOS:

```bash
docker buildx imagetools inspect --raw eclipse-temurin:17-jre |
  jq -r '.manifests[]? |
         select(.platform.os == "linux") |
         "\(.platform.os)/\(.platform.architecture)"'
```

Script này chỉ phù hợp khi reference trả về **index/list** với field `manifests`; một **single-platform manifest** không có array đó, nên output rỗng không nhất thiết có nghĩa image không có platform. Hãy kiểm tra mediaType và trường `config` nếu output không phải index.

### 5.2. Nhìn lại digest đang pin

Quy trình thủ công đáng tin:
1. Chọn tag theo policy (`17-jre` hoặc tag cụ thể hơn).
2. Chạy `docker buildx imagetools inspect IMAGE:TAG`.
3. Đọc dòng `Digest: sha256:...` ở **cấp reference/index** nếu cần pin multi-platform.
4. Kiểm tra `Manifests` chứa `linux/amd64` và `linux/arm64` theo yêu cầu.
5. Copy **nguyên văn** digest thực vào Dockerfile hay manifest cấu hình CI; review diff.
6. Lưu provenance nguồn registry, thời điểm kiểm tra, tag human-readable và security scan report.

**Không chép một digest tìm thấy trong ví dụ trên mạng hoặc tự viết 64 ký tự giả.** Digest phải được lấy từ publisher/registry mà CI thực sự truy cập, vì digest của image qua mirror/retag/rebuild có thể khác.

### 5.3. Phân biệt remote registry inspect và local image inspect

`docker buildx imagetools inspect`: xem manifest/index **ở registry**. `docker image inspect`: xem image/config có trong **local image store**, thường là biến thể đã pull/loaded.

Ví dụ:

```bash
docker pull --platform linux/amd64 eclipse-temurin:17-jre
docker image inspect --format '{{.Os}}/{{.Architecture}}' eclipse-temurin:17-jre
```

Với local store chứa đúng variant AMD64, output tương ứng:

```text
linux/amd64
```

Nếu local store hỗ trợ multi-platform và có nhiều biến thể, có thể cần lựa chọn platform khi inspect (tùy Docker API/Engine version). Vì vậy để audit **mọi variant trong registry**, ưu tiên `imagetools inspect` thay vì dựa vào một local `image inspect`.

## 6. Chọn chiến lược version cho base image

### 6.1. Ba kiểu reference phổ biến

```dockerfile
# A. Tag dễ cập nhật nhưng mutable:
FROM eclipse-temurin:17-jre

# B. Tag hẹp hơn, vẫn có thể mutable:
FROM eclipse-temurin:17-jre-jammy

# C. Pin bằng digest:
# FROM eclipse-temurin:17-jre@sha256:<digest thực tế do registry trả về>
```

Dòng C được comment vì cần digest thật, không thể chạy nguyên trạng. **A và B là ví dụ Dockerfile hợp lệ**, giả định publisher còn cung cấp các tag đó. Cú pháp thực khi pin:

```text
FROM image:human-readable-tag@sha256:64-hex-digit-digest
```

Sơ đồ cú pháp trên không phải Dockerfile thực. Không sử dụng text mô tả làm digest; thay bằng giá trị đã kiểm tra.

### 6.2. Bảng quyết định

| Chiến lược | Tái lập base image | Nhận bản vá tự động qua tag | Công việc vận hành |
| --- | --- | --- | --- |
| `:latest` | Thấp | Có thể | Rủi ro cập nhật bất ngờ cao |
| `:17-jre` | Không đảm bảo | Thường có khi rebuild/pull mới | Cần test sau tag move |
| `:17-jre-jammy` | Không đảm bảo | Có thể trong dòng distro/Java đó | Kiểm soát OS family tốt hơn |
| `:tag@sha256:index` | Pin chính xác index đa nền tảng | **Không tự động đổi** | Theo dõi và cập nhật digest chủ động |
| `@sha256:platform-manifest` | Pin một biến thể duy nhất | Không tự động đổi | Quản lý từng architecture riêng |
| Registry có immutable tag policy | Tốt trong phạm vi registry/policy | Phụ thuộc quy trình mới tạo tag | Phải kiểm chứng policy và retention |

**Khuyến nghị thực tiễn:** production/release nên biết **đúng digest** của mọi base image. Pin digest khi cần audit và reproducibility; đồng thời có quy trình cập nhật định kỳ và trigger theo CVE. Trong development có thể dùng tag ngắn gọn để thử nghiệm, nhưng không nên để CD kéo một tag mutable mà không ghi nhận image digest.

## 7. Không khóa cứng CPU trong Dockerfile nếu cần build đa kiến trúc

Một anti-pattern:

```dockerfile
FROM --platform=linux/amd64 eclipse-temurin:17-jre
```

Dòng này ép stage dùng AMD64. Nếu gọi `docker buildx build --platform linux/amd64,linux/arm64`, giá trị cố định trong `FROM` có thể khiến image ARM64 chứa binary/runtime AMD64, hoặc làm build thất bại/cảnh báo. Docker Build Check `FromPlatformFlagConstDisallowed` khuyến nghị **không hardcode platform** trong FROM khi mục tiêu hỗ trợ multi-platform.

**Đúng với stage runtime:**

```dockerfile
FROM eclipse-temurin:17-jre
```

Khi xây:

```bash
docker buildx build --platform linux/amd64 .
docker buildx build --platform linux/arm64 .
```

Docker/BuildKit chọn base variant cho **target platform** theo lệnh build. Chạy không `--platform` thường chọn platform mặc định của builder, không phải architecture của mọi node production.

### 7.1. BUILDPLATFORM và TARGETPLATFORM khác nhau

BuildKit tự cung cấp một số automatic platform arguments:

| ARG | Ý nghĩa | Giá trị ví dụ |
| --- | --- | --- |
| `BUILDPLATFORM` | Platform máy/node thực thi builder | `linux/arm64` |
| `BUILDOS`, `BUILDARCH` | Các thành phần OS/CPU của builder | `linux`, `arm64` |
| `TARGETPLATFORM` | Platform yêu cầu cho output image | `linux/amd64` |
| `TARGETOS`, `TARGETARCH` | OS và CPU của output image | `linux`, `amd64` |
| `TARGETVARIANT` | Variant cụ thể nếu có | `v7`, `v8` hoặc rỗng |

Ví dụ xây AMD64 image trên laptop ARM64:

```text
BUILDPLATFORM = linux/arm64
TARGETPLATFORM = linux/amd64
```

Hai giá trị không bắt buộc giống nhau. Đặc biệt trong multi-stage build, có thể chạy stage **biên dịch Java thuần** trên native build platform rồi tạo final runtime image trên target platform.

### 7.2. ARG có scope: muốn dùng trong RUN phải khai báo lại

BuildKit cung cấp `BUILDPLATFORM`/`TARGETPLATFORM` ở global scope cho `FROM`, nhưng để sử dụng trong lệnh `RUN` của một stage, phải thêm `ARG` vào stage:

```dockerfile
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM alpine:3.21 AS diagnostic

ARG BUILDPLATFORM
ARG TARGETPLATFORM
ARG TARGETARCH

RUN printf 'builder=%s target=%s arch=%s\n' \
    "$BUILDPLATFORM" "$TARGETPLATFORM" "$TARGETARCH"
```

Đây là **ví dụ chẩn đoán Dockerfile fragment**, không phải Dockerfile ứng dụng Java hoàn chỉnh. Tag `alpine:3.21` có thể thay đổi và phải pin digest nếu yêu cầu production reproducibility. `RUN` trên stage này chạy theo build platform, còn target có thể khác.

**Lưu ý:** `FROM --platform=$BUILDPLATFORM` là lựa chọn có chủ đích cho **build stage**, không nên áp vào **final runtime stage** khi muốn output theo `TARGETPLATFORM`.

## 8. Ví dụ Spring Boot Java 17 đủ để tự build và chạy

Ta tạo một API nhỏ có:
- `GET /ready` trả response ổn định `ready`.
- `GET /arch` trả Java runtime architecture qua `System.getProperty("os.arch")`, giúp quan sát JRE variant.

### 8.1. Cấu trúc project

```text
base-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
└── src/
    └── main/
        └── java/
            └── com/example/base/
                └── BaseDemoApplication.java
```

Cần Docker Buildx/BuildKit và mạng để builder tải Maven/plugins, cùng registry base. Muốn chạy Maven trên host thì cần JDK 17+ và Maven 3.9.x tương thích. Với multi-platform ARM trên AMD64 (hoặc ngược lại), phải có builder hỗ trợ architecture đó qua QEMU hoặc native nodes.

### 8.2. File pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>base-demo</artifactId>
    <version>0.1.0</version>
    <packaging>jar</packaging>
    <name>base-demo</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot starter parent quản lý dependency/plugin versions; `spring-boot-maven-plugin` được khai báo để `repackage` tạo executable JAR tại Maven `package`.

### 8.3. Java code runnable

**`src/main/java/com/example/base/BaseDemoApplication.java`:**

```java
package com.example.base;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BaseDemoApplication.class, args);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/arch")
    public String arch() {
        return System.getProperty("os.arch");
    }
}
```

`System.getProperty("os.arch")` trả tên architecture theo Java runtime/OS, **không nhất thiết trùng chính xác** tên Docker architecture label. Trên Linux AMD64 thường là `amd64`, còn ARM64 thường là `aarch64`; phải kiểm tra giá trị thật thay vì hardcode làm gate không có mapping.

### 8.4. Kiểm tra trên host, không cần Docker

```bash
mvn -B -ntp clean package
java -jar target/base-demo-0.1.0.jar
```

Ở terminal khác:

```bash
curl -fsS http://localhost:8080/ready
```

**Response body chính xác:** `ready` (không tự thêm newline). `GET /arch` trả string `os.arch` của **JVM đang chạy trên host**, không phải Docker build target. Dừng server bằng Ctrl+C.

## 9. Dockerfile đa giai đoạn dùng tag, có thể thay bằng digest

**`Dockerfile` hoàn chỉnh:**

```dockerfile
# syntax=docker/dockerfile:1

ARG BUILD_IMAGE=maven:3.9-eclipse-temurin-17
ARG RUNTIME_IMAGE=eclipse-temurin:17-jre

FROM --platform=$BUILDPLATFORM ${BUILD_IMAGE} AS build
WORKDIR /workspace

COPY pom.xml ./
COPY src ./src

RUN mvn -B -ntp clean package

FROM ${RUNTIME_IMAGE} AS runtime
WORKDIR /app

COPY --from=build /workspace/target/base-demo-0.1.0.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Giải thích chính xác:**

1. `ARG BUILD_IMAGE` và `ARG RUNTIME_IMAGE` khai báo **trước FROM** để có thể tham chiếu trong tên base image. Giá trị mặc định là tag dễ chạy thử, vẫn **mutable**.
2. `FROM --platform=$BUILDPLATFORM ... AS build` chạy Maven/JDK trên architecture của builder. Vì demo chỉ sinh **Java bytecode/JAR không có native build output**, cùng JAR có thể được copy sang runtime stage AMD64 hoặc ARM64.
3. `FROM ${RUNTIME_IMAGE} AS runtime` **không** gắn một platform cố định; Buildx tự chọn đúng runtime variant theo target.
4. `COPY --from=build .../base-demo-0.1.0.jar` lấy **đúng Maven executable JAR**, không mang compiler, source code hay `~/.m2` sang runtime.
5. `USER 10001` chạy ứng dụng không phải root; app chỉ cần đọc file JAR và mở port 8080 (không phải privileged port). File copy có quyền đọc phù hợp trong image build thông thường.
6. `ENTRYPOINT` ở exec form chuyển tín hiệu tới process Java dễ hơn dạng shell không có `exec`.
7. `EXPOSE 8080` chỉ là metadata; khi chạy phải publish port/mapping nếu muốn host truy cập.

### 9.1. Vì sao không đóng base digest giả trong bài?

Digest phụ thuộc đối tượng thật trên registry. Nếu viết một `sha256` tưởng tượng trong Dockerfile, lệnh `docker build` sẽ fail hoặc tệ hơn làm người học tin nhầm image đã được pin.

Dockerfile ở trên **runnable với tag**, còn CI có thể truyền reference đã pin mà **không sửa source**:

```bash
docker buildx build \
  --build-arg RUNTIME_IMAGE=eclipse-temurin:17-jre \
  -t base-demo:local \
  --load .
```

Khi đã lấy được digest thực cho **index hoặc manifest** từ `docker buildx imagetools inspect eclipse-temurin:17-jre`, truyền cùng reference ở dạng `eclipse-temurin:17-jre@sha256:<digest-thực-tế>` vào `RUNTIME_IMAGE`. Áp dụng tương tự với `BUILD_IMAGE` nếu cần pin cả Maven builder.

**Quan trọng:** chỉ pin runtime nhưng để `maven:3.9-eclipse-temurin-17` và Dockerfile frontend tiếp tục mutable vẫn có thể khiến output thay đổi vì compiler/plugin/tooling hoặc quá trình giải quyết dependency. Reproducibility end-to-end đòi pin/kiểm tra **toàn bộ build chain**, không chỉ final JRE base.

### 9.2. File .dockerignore

**`.dockerignore`:**

```dockerignore
.git
.idea
.vscode
target
build
.gradle
**/node_modules
.env
*.pem
*.key
*.p12
```

Dockerfile trên chỉ COPY `pom.xml` và `src` nên ít nguy cơ copy thừa, nhưng `.dockerignore` vẫn giảm build context, bảo vệ dữ liệu local và tránh vô tình đóng file nhạy cảm khi Dockerfile sau này thay đổi. Nó **không bảo vệ** secret đã nằm trong `src/main/resources`; phải giữ secrets ngoài source và cấp qua runtime secret mechanisms.

### 9.3. Khi nào build stage native không an toàn?

Cách `FROM --platform=$BUILDPLATFORM ... AS build` thích hợp khi đầu ra là **Java bytecode trung lập về CPU**. Nhưng nếu dự án:
- biên dịch JNI/shared libraries `.so`;
- chứa native-image/GraalVM outputs;
- tải binary theo `uname -m` trong build;
- generate arch-specific artifacts;
- có annotation/code generator phụ thuộc CPU hoặc native libc;

thì JAR và native components có thể **không portable**. Cần build riêng cho `TARGETARCH`, cross-compile đúng toolchain hoặc chạy build stage trên target-native builder. Không copy binary ARM64 từ builder vào runtime AMD64 (hoặc ngược lại).

## 10. Build image một kiến trúc và xác minh runtime

### 10.1. Single-platform build ở local

Khi máy/builder hỗ trợ AMD64:

```bash
docker buildx build \
  --platform linux/amd64 \
  -t base-demo:amd64 \
  --load .
```

`--load` nạp kết quả single-platform vào local Docker image store trong cấu hình Buildx phổ biến. Với các builder/engine hiện đại hỗ trợ multi-platform image store, khả năng load có thể khác; ví dụ này **chỉ yêu cầu một platform**.

Run:

```bash
docker run --rm \
  --platform linux/amd64 \
  -p 127.0.0.1:8080:8080 \
  base-demo:amd64
```

Terminal khác:

```bash
curl -fsS http://localhost:8080/ready
```

**Response body:** `ready`.

Kiểm tra image platform trong local store:

```bash
docker image inspect \
  --format '{{.Os}}/{{.Architecture}}' \
  base-demo:amd64
```

**Kết quả kỳ vọng khi đúng variant:** `linux/amd64`. `docker image inspect` và `docker buildx imagetools inspect` khác nhau: một cái xem local image config, cái kia xem remote registry manifest/index.

### 10.2. Thử ARM64

Nếu builder và host hoặc emulator có hỗ trợ:

```bash
docker buildx build \
  --platform linux/arm64 \
  -t base-demo:arm64 \
  --load .
```

Chạy ARM64 image trên host AMD64 đòi **emulation/runtime support** thích hợp; nếu thiếu, có thể gặp `exec format error`. Một cách đáng tin hơn là chạy image trên **ARM64 node thật** trong CI/cloud.

`GET /arch` trên hai kiến trúc có thể trả `amd64`/`aarch64` từ Java, nhưng Docker image platform phải được kiểm tra bằng manifest/image metadata. Không dùng string `os.arch` làm bằng chứng tuyệt đối của OCI index metadata.

## 11. Build và push một image hỗ trợ AMD64 + ARM64

### 11.1. Kiểm tra builder hỗ trợ gì

```bash
docker buildx version
docker buildx ls
docker buildx inspect --bootstrap
```

Output của `inspect --bootstrap` thường có các platforms builder có thể xử lý. Nếu builder hiện tại không hỗ trợ multi-platform, một cấu hình thường dùng là driver `docker-container`:

```bash
docker buildx create \
  --name multiarch-builder \
  --driver docker-container \
  --use \
  --bootstrap
```

Lệnh tạo builder chỉ chạy nếu chưa có builder cùng tên; nếu đã có, sử dụng builder hiện hữu. Docker Desktop thường có setup binfmt/QEMU sẵn; Docker Engine trên Linux tùy môi trường có thể cần QEMU/binfmt hoặc builder nodes riêng. Không cài QEMU tự động lên máy production chỉ để thử multi-platform build; dùng CI builder được quản lý.

**Ba chiến lược:**
1. **QEMU emulation:** setup nhanh nhưng có thể rất chậm cho Maven/apt/native compile.
2. **Native AMD64 + ARM64 builder nodes:** tốc độ/khả năng tương thích tốt hơn, cần hạ tầng.
3. **Cross-compilation:** phù hợp khi language/toolchain hỗ trợ; với Java bytecode thuần có thể build một lần trên native builder rồi copy sang nhiều runtime variants như demo.

### 11.2. Publish multi-platform index vào registry

Cần có quyền push tới một image repository hợp lệ; trong CI, biến môi trường `IMAGE_REF` chứa reference cụ thể do pipeline cấp, ví dụ một repository nội bộ gắn release version.

```bash
: "${IMAGE_REF:?Set IMAGE_REF to a writable registry image tag}"

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "$IMAGE_REF" \
  --push .
```

`: "${IMAGE_REF:?...}"` là cú pháp Bash **fail-fast** nếu biến chưa được đặt; không chứa credential và không tự giả định tên registry của người học. CI phải cung cấp credentials qua `docker login` hoặc credential helper an toàn, không hardcode password trong Dockerfile, `ARG` hoặc Git.

`--push` publish image variants và manifest list/OCI index; dùng nó khi xây multi-platform trên builder `docker-container`. Nếu dùng `--load` cho nhiều platforms, kết quả phụ thuộc image store/Engine capability, nên hướng dẫn chung dễ tái lập nhất là **push vào registry rồi inspect manifest ở đó**.

### 11.3. Kiểm tra index sau push

```bash
docker buildx imagetools inspect "$IMAGE_REF"
```

Phải thấy ít nhất `linux/amd64` và `linux/arm64`. Nếu cần kiểm tra bằng JSON với `jq`:

```bash
docker buildx imagetools inspect --raw "$IMAGE_REF" |
  jq -r '.manifests[]? |
         select(.platform.os == "linux") |
         "\(.platform.os)/\(.platform.architecture)"'
```

Với Buildx có SBOM/provenance attestations, các entries `unknown/unknown` có thể xuất hiện trong index; **đừng coi đó là lỗi CPU** nếu index vẫn có đúng platform variants cần thiết. Ngược lại, nếu index chỉ có `linux/amd64`, việc tag mang tên “multiarch” không biến nó thành multi-platform image.

### 11.4. Kiểm chứng bằng pull/run theo platform

Ở runner AMD64:

```bash
docker pull --platform linux/amd64 "$IMAGE_REF"
docker run --rm --platform linux/amd64 \
  -p 127.0.0.1:8080:8080 "$IMAGE_REF"
```

Ở runner ARM64 (hoặc có emulator hợp lệ), thay bằng `--platform linux/arm64`. Endpoint `/ready` luôn phải trả `ready`. Với image đa kiến trúc, mỗi runner có thể lấy **child digest/layers khác nhau** dù dùng chung tag/index. Đó là hành vi đúng.

## 12. Pin index digest cho multi-architecture deployment

Quy trình release:

1. CI build và push `IMAGE_REF` đã qua unit/smoke tests.
2. Chạy `docker buildx imagetools inspect "$IMAGE_REF"` để đọc **index digest** của image đã push.
3. Kiểm tra cả `linux/amd64` và `linux/arm64` có trong `Manifests`.
4. Ghi `repository@sha256:<index-digest-thực-tế>` vào release manifest, deployment descriptor, SBOM/provenance.
5. Khi triển khai, dùng **reference có digest** thay vì để mutable tag thay đổi ngầm.
6. Định kỳ scan và nâng base image digest theo quy trình có kiểm thử; việc pin **không loại bỏ trách nhiệm vá CVE**.

Ví dụ **ký pháp triển khai**:

```text
registry.example.org/team/base-demo@sha256:<real-index-digest>
```

Đây chỉ là **mẫu định dạng**, chưa phải reference dùng được: registry/repository ở đây minh họa và digest phải là giá trị thật. Không tạo một digest ngẫu nhiên cho tài liệu.

**Phân biệt:** pin digest của **output application image** khi deploy và pin digest của **input base image** khi build là hai việc khác nhau. Một bản phát hành đáng tin ghi được cả:
- source Git commit;
- builder/runtime base image digests;
- Java/Maven/plugin versions;
- application image index digest và per-platform manifests;
- scan/test/attestation evidence.

### 12.1. Có cần ép --platform trong Dockerfile khi pin index?

Không. Với index digest multi-platform, Dockerfile có thể viết:

```dockerfile
FROM eclipse-temurin:17-jre@sha256:<verified-index-digest>
```

Đây là **cú pháp minh họa, chưa chạy được khi chưa thay digest thật**. Giữ `FROM` không `--platform=linux/amd64`; chọn target bằng:

```bash
docker buildx build --platform linux/amd64 ...
docker buildx build --platform linux/arm64 ...
```

Docker/BuildKit sẽ giải quyết variant trong **index cố định**. Nếu bạn pin **child manifest AMD64** thay vì index, build ARM64 có thể lỗi vì không có variant phù hợp. Vì vậy phải đọc cấu trúc manifest và xác định bạn đang lấy digest ở **cấp nào**.

## 13. Dockerfile build arguments: thiết kế để pin nhưng vẫn dễ cập nhật

Dockerfile ở mục 9 cho phép truyền base references qua `--build-arg`. Điều này giúp:
- source Dockerfile được review và không chứa digest copy sai;
- CI có thể pin digest theo release configuration;
- cùng một Dockerfile build từ dev tag đến release digest;
- cập nhật base độc lập với Java source khi cần vá bảo mật.

Nhưng cũng có rủi ro: nếu pipeline truyền `RUNTIME_IMAGE` sai hoặc rỗng, build sẽ fail hoặc lấy default tag mutable.

**Khuyến nghị CI:**
- Dev builds cho phép default tag.
- Release builds **bắt buộc** set `BUILD_IMAGE`/`RUNTIME_IMAGE` sang pinned digest references; xác minh chúng trỏ cùng registry/provider được duyệt.
- Log **base image references và digests**, không log private registry credentials.
- Không đặt secrets trong `ARG` hoặc `ENV`: thông số có thể xuất hiện trong image metadata/history/build logs.
- Nếu dùng registry mirror, đối chiếu digest từ đúng mirror/source.
- Khai báo default hợp lệ trong `ARG` để Docker build check `InvalidDefaultArgInFrom` không fail, hoặc có cơ chế kiểm tra rõ đầu vào của build pipeline.

### 13.1. Vì sao tag + digest cùng xuất hiện?

`FROM eclipse-temurin:17-jre@sha256:<digest>` giúp người đọc biết dòng Java/runtime mong muốn, còn digest quyết định chính xác manifest/index. Khi publisher di chuyển tag `17-jre`, build vẫn dùng digest đã pin (nếu registry còn cung cấp).

**Không tự động đổi digest mỗi lần build rồi gọi đó là pin.** Nếu CI mỗi lần đều resolve tag thành digest mới và ngay lập tức build, điều đó ghi lại input thực tế nhưng chưa cho phép kiểm duyệt thay đổi base. Pipeline release tốt nên update digest qua PR/change review, scan, test, rồi publish version mới.

## 14. Base image selection liên quan bảo mật và support lifecycle

### 14.1. JDK vs JRE

- **Build stage** cần JDK, Maven/Gradle và các toolchain liên quan.
- **Runtime stage** thường chỉ cần JRE tương thích Java bytecode (ví dụ Java 17), không cần Maven/compiler.
- Multi-stage Dockerfile giúp giảm image surface bằng cách không mang công cụ build vào runtime.
- Với AppCDS, jlink, native-image hoặc các feature đặc thù, yêu cầu runtime có thể khác; kiểm chứng trên distro/arch cụ thể.

### 14.2. Chọn distro/variant phù hợp

Khi chọn `eclipse-temurin:17-jre` hoặc tag có distro suffix:
- đọc publisher docs về Debian/Ubuntu/Alpine variants, patch cadence và supported architectures;
- kiểm tra `linux/arm64` có tồn tại; không suy luận từ tên tag;
- kiểm tra native dependencies, locale, TLS certificates, timezone, fonts nếu app có nhu cầu;
- đảm bảo Java 17 được hỗ trợ trong thời gian vận hành dự kiến;
- kiểm tra user non-root và required filesystem permissions.

**Không mặc định image nhỏ nhất là an toàn nhất.** Distroless/minimal có thể giảm package surface nhưng khiến debug khó hơn và cần cách cấp CA/tzdata/native libraries đúng.

### 14.3. Security scanning và SBOM

Pin digest giúp tái lập base **đã biết**, nhưng nếu base đó có CVE, nó vẫn có CVE trong các lần build sau. CI nên:
- scan base và final image bằng giải pháp được tổ chức phê duyệt (Docker Scout hoặc công cụ tương đương);
- ghi SBOM, provenance/attestation khi cần;
- theo dõi update của publisher và automated dependency/base-image PRs;
- kiểm tra changelog, CVE fix và compatibility;
- rebuild, run unit/integration tests, scan lại và rollout có canary/rollback;
- ghi lại old/new index digests, platforms và image digest output.

### 14.4. Tag mutable không đồng nghĩa luôn lấy bản mới

Docker có build cache, local images và pull policies. Cùng Dockerfile tag-only có thể giữ cache/layer cũ trong một workflow, hoặc lấy manifest mới trong workflow khác tùy builder/cache/pull. Khi chủ đích kiểm tra tag đã cập nhật, dùng chế độ pull theo workflow Docker/buildx thích hợp và xác nhận manifest digest thực tế; không dựa vào giả định “mỗi build tự có bản vá mới”.

Dù dùng `--pull`, **pin digest cũ vẫn chọn đối tượng cũ**: `--pull` kiểm tra/tải lại đúng reference, không biến digest cố định thành tag mới.

## 15. Lỗi kiến trúc CPU thường gặp trong Java/Spring Boot

| Dấu hiệu | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| `exec format error` ngay khi container start | Image binary/entrypoint không hợp kiến trúc host; không có emulation | Kiểm tra platform manifest, dùng đúng variant hoặc native node/QEMU |
| `no match for platform in manifest` | Tag/digest không có platform được yêu cầu | `imagetools inspect` xem list; chọn base khác |
| ARM64 build nhanh/ổn nhưng AMD64 build fail | Native dependency/JNI/JDK distribution lệch kiến trúc | Test từng platform, xem build/runtime stages |
| QEMU build rất chậm | Chạy nhiều lệnh Maven/apt dưới emulation | Dùng `--platform=$BUILDPLATFORM` cho Java-only build stage hoặc native nodes |
| Java báo `UnsatisfiedLinkError` | Native library trong app không khớp architecture/libc | Đóng gói đúng JNI binary theo target platform |
| `java: not found` trong runtime image | Chọn base không có JRE hoặc PATH khác | Chọn đúng JRE image và kiểm tra entrypoint |
| `UnsupportedClassVersionError` | Build JDK phát bytecode mới hơn runtime | Dùng `--release 17`/toolchain phù hợp, runtime Java 17+ |
| `linux/arm64` chạy trên AMD64 host không được | Thiếu QEMU hoặc engine không hỗ trợ platform đó | Dùng ARM64 runner hoặc cài emulation ở builder được quản lý |
| Ảnh push lên registry chỉ có AMD64 | Buildx command chỉ có một `--platform` hoặc push sai output | Build `--platform linux/amd64,linux/arm64 --push` rồi inspect index |
| Dockerfile `FROM --platform=linux/amd64` bị lint cảnh báo | Hardcode một platform trong stage cần multiarch | Bỏ platform của final FROM, dùng CLI `--platform` |
| `docker image inspect` thấy AMD64 còn index có ARM64 | Local image store chỉ nạp AMD64 variant | Dùng `imagetools inspect` remote index và pull platform phù hợp |
| Container có Java 17 nhưng TLS/locale/native lỗi | Base distro/library/CA/tzdata khác | Chọn distro support phù hợp và test runtime behavior |
| Image trên một K8s node chạy, node khác pull fail | Manifest thiếu platform mới, node label/OS khác | Pin multi-platform index, check node architecture và scheduling |

### 15.1. Kiểm tra architecture bằng công cụ đúng

**Ở registry:** `docker buildx imagetools inspect REFERENCE` để xem các platform manifests.

**Ở local:** `docker image inspect --format '{{.Os}}/{{.Architecture}}' IMAGE` xem image config local.

**Bên trong container:** có thể dùng `uname -m` nếu image có shell/coreutils, hoặc `System.getProperty("os.arch")` để xem Java runtime. Các string này **không nhất thiết trùng cách viết** với `linux/amd64`/`linux/arm64` của Docker metadata.

**Ở builder:** `docker buildx inspect --bootstrap` xem platforms được builder hỗ trợ.

Đừng dùng **chỉ `uname -m` trên host laptop** để suy ra platform của CI builder hoặc final image: Docker Desktop VM, remote context và Buildx builder nodes có thể khác.

## 16. Kubernetes và kiến trúc CPU

Với multi-platform image index, kubelet/container runtime thường chọn child image phù hợp node platform khi kéo từ registry. Kubernetes nodes thường có labels:

```text
kubernetes.io/os=linux
kubernetes.io/arch=amd64
kubernetes.io/arch=arm64
```

Nếu application image chỉ publish AMD64 variant, workload được schedule lên ARM64 node có thể không pull/run được. Có thể giới hạn scheduling trong manifest Deployment:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/os: linux
        kubernetes.io/arch: amd64
```

Đây chỉ là **đoạn YAML của Deployment pod template**, không phải Kubernetes Deployment file độc lập. Nó giới hạn node selection tới Linux AMD64; không biến image thành AMD64. Nếu đã publish/test index gồm AMD64 và ARM64, thường không cần nodeSelector theo arch cho Java-only workloads, trừ khi có lý do như native dependency, hiệu năng hay support policy.

**Quan trọng:**
- Một `image: repository:tag` mutable và `imagePullPolicy: Always` không phải pin immutable release. Với yêu cầu audit, dùng `image: repository@sha256:<index-digest-thực-tế>`.
- Nếu tag/digest trỏ index multi-platform, node chọn child platform thích hợp; cần xác minh runtime/registry hỗ trợ loại manifest này.
- Pod spec chứa Java process args/config độc lập với CPU image variant; ứng dụng vẫn phải có readiness/liveness probes phù hợp.
- Với cluster mixed-arch, test hai kiến trúc trên nodes thật; không chỉ test emulated build.
- Rolling upgrade khi base digest thay đổi phải có kiểm thử khả năng rollback và monitor runtime/GC/TLS errors.

## 17. CI kiểm tra architecture coverage và đúng base digest

Một pipeline mạnh nên có hai loại dữ liệu:
1. **Base references:** builder + runtime image pinned, nguồn registry và CPU variants.
2. **Output release:** ứng dụng container index digest, list child manifests, SBOM, scan evidence.

### 17.1. Gating theo danh sách platform bắt buộc

Giả sử `IMAGE_REF` đã được CI set tới remote application image sau push và `jq` có sẵn. Bash:

```bash
set -eu
: "${IMAGE_REF:?IMAGE_REF must be set by CI}"

docker buildx imagetools inspect --raw "$IMAGE_REF" |
  jq -e '
    [ .manifests[]?
      | select(.platform.os == "linux")
      | .platform.architecture
    ] as $arch
    | ($arch | index("amd64") != null)
      and ($arch | index("arm64") != null)
  '
```

Với multi-platform index hợp lệ chứa AMD64+ARM64, `jq -e` trả exit code 0 (và in `true`). Nếu thiếu một architecture, trả non-zero và job fail. Đây là check minh họa cho **index/list**, không phải single-platform manifest; cần bổ sung logic nếu policy cho phép single-platform images.

### 17.2. Pin cả inputs và outputs

Đối với release:
- Capture base references **sau khi xác thực** từ Docker Hub/registry được duyệt.
- Cấu hình Dockerfile/CI để dùng `tag@sha256:index` hoặc một chính sách digest đủ rõ.
- Build/push output image với version/commit tag hợp lệ và immutable release record.
- Capture **output index digest** sau push, publish theo digest vào deployment.
- Scan cả platform manifests; CVE/native package list có thể khác giữa AMD64/ARM64.
- Chạy smoke tests trên từng platform được support.
- Khi publisher cập nhật base, mở PR thay digest, chạy regression và quay vòng deployment; không sửa digest production bằng tay thiếu review.

### 17.3. Ví dụ quality gates có ích

| Gate | Dữ liệu vào | Kết quả mong đợi |
| --- | --- | --- |
| Lint Dockerfile | Dockerfile + BuildKit | Không hardcode final `FROM --platform=linux/amd64` nếu phát hành multiarch |
| Base manifest coverage | Pinned base index | Có `linux/amd64` và `linux/arm64` |
| Toolchain | Maven/JDK/plugin versions | Java 17-compatible executable JAR |
| Image publish | Buildx multi-platform build | Có output index và per-platform manifests |
| Runtime smoke | Containers trên AMD64/ARM64 | `GET /ready` trả `ready` |
| Security | Scan/SBOM/base provenance | Không có issue vượt policy |
| Reproducibility | Immutable base refs + pinned build inputs | Artifact/digest đủ khả năng truy vết |
| Deployment | Release image index digest | Node nhận variant đúng và readiness đạt |
| Update policy | CVE/base update trigger | PR cập nhật có test và rollback plan |

**Đừng chỉ kiểm tra tag tồn tại trong registry.** Một tag có thể chỉ chứa một platform, hoặc trỏ sang index mới đã bỏ ARM64. Mỗi lần thay digest phải xác minh architecture coverage.

## 18. Phân biệt tag, digest và trust

Digest hỗ trợ **content addressing**, nhưng không tự chứng minh image được tạo bởi publisher đáng tin cậy. Một image độc hại vẫn có digest hợp lệ của chính nó.

Muốn đánh giá **trust**:
- Chọn registry/repository được phê duyệt.
- Kiểm tra publisher, image signing, provenance/attestation và SBOM theo supply-chain policy.
- Scan OS packages/JRE và dependencies của ứng dụng.
- Pin digest sau khi xác minh nguồn.
- Kiểm soát quyền push/tag mutation của registry và retention policy.
- Không sử dụng tag `latest` hoặc digest lấy từ nguồn không xác thực để thay base production.
- Theo dõi rebase/update cadence, vì digest pin cũ không tự nhận vulnerability fixes.

Một digest có thể **định danh chính xác nhưng không còn tải được** nếu registry xóa manifests/layers theo retention. Reproducible build cần lưu giữ dependencies, mirror và artifact provenance, không chỉ commit Dockerfile.

## 19. Trường hợp nâng cao: image index và native-image

### 19.1. Java JAR không giống native executable

Một Spring Boot JAR biên dịch `.class` thuần và chạy trên Temurin JRE phù hợp thường portable giữa AMD64/ARM64. Nhưng nếu bạn chuyển sang **Spring Boot native image**:
- binary được build cho một OS/arch/ABI cụ thể;
- không thể lấy AMD64 native binary rồi đặt vào ARM64 runtime stage;
- phải cross-compile đúng hoặc build native trên runner target;
- mỗi variant image có digest riêng và index có thể tổng hợp chúng;
- BuildKit `TARGETARCH`/`BUILDARCH` cần được đưa vào toolchain đúng cách.

Do đó Dockerfile Java-only ở mục 9 **không phải** mẫu có thể copy nguyên xi cho GraalVM native-image hoặc ứng dụng JNI phức tạp.

### 19.2. AMD64 vs ARM64 hiệu năng, tính năng khác nhau

Hai kiến trúc có thể khác hiệu năng JIT/GC, vector instructions, native compression, TLS crypto và JVM flags được hỗ trợ. Build multiarch pass không đồng nghĩa performance/correctness tương đương. Với dịch vụ latency-sensitive, cần benchmark trên CPU thật, kiểm tra memory limits và flags JVM, chứ không chỉ dựa vào QEMU smoke test.

### 19.3. Index digest và per-platform child digests trong release

Một release multiarch thường cần cả:
- **index digest**: một reference chung cho manifest list/image index;
- **child digest AMD64/ARM64**: phục vụ kiểm toán variant cụ thể, runtime package scan, SBOM tương ứng.

Nếu tổ chức phải khóa node architecture nhất định, có thể deploy child digest đó **theo platform**. Nhưng khi dùng cùng deployment descriptor cho cluster mixed-arch, **pin index** thường tiện hơn và tránh tham chiếu nhầm child AMD64 vào ARM64 node.

## 20. Câu hỏi thường gặp

**Q1. `FROM eclipse-temurin:17-jre` có tự chọn ARM64 trên Apple Silicon không?**

Nếu builder target là `linux/arm64` và registry tag có ARM64 variant, BuildKit chọn biến thể phù hợp. Docker Desktop, remote builders và `--platform` flags có thể đổi target; không tự suy từ laptop nếu đang dùng builder remote.

**Q2. Dockerfile có cần `FROM --platform=$TARGETPLATFORM` không?**

Thông thường **không cần**, vì target platform đã là mặc định cho FROM không có override. Docker check còn cảnh báo trường hợp chỉ viết một lựa chọn dư thừa. Chỉ dùng `--platform=$BUILDPLATFORM` cho build stage khi có mục đích rõ; final runtime để target mặc định.

**Q3. Pin `tag@sha256` có còn nhận security patch tự động không?**

Không. Tag có thể cập nhật, nhưng digest đã pin vẫn giữ đối tượng cũ. Cần cập nhật digest một cách chủ động với scan/test.

**Q4. `docker buildx build --platform linux/amd64,linux/arm64 --load` luôn hoạt động chứ?**

Không nên giả định. Khả năng load multi-platform phụ thuộc builder driver/image store; với `docker-container` driver, chiến lược phổ biến là `--push` đến registry hỗ trợ manifest list rồi inspect. `--load` single-platform đơn giản hơn cho local.

**Q5. Tại sao `java -version` giống nhau trên hai node mà image SHA khác?**

Vì image config, JRE native binaries, OS packages và per-architecture layers khác, hoặc publisher đã cập nhật tag. Cùng Java feature version không chứng minh cùng bytes.

**Q6. `docker image inspect .Id` có phải digest để pin Dockerfile không?**

Không nhất thiết. `.Id` thường là image config digest; `FROM repository@sha256:...` cần manifest/index digest có thể resolve từ registry. Dùng `imagetools inspect` theo yêu cầu.

**Q7. Có thể pin cùng index digest cho AMD64 và ARM64 không?**

Có, **nếu** digest thực sự của multi-platform index chứa cả hai variants. Builder/puller sẽ chọn child manifest theo platform. Pin child manifest AMD64 thì không đạt cùng kết quả.

**Q8. Nếu tôi dùng `ubuntu:latest` trong builder và `eclipse-temurin:17-jre` ở runtime, chỉ pin runtime đã đủ chưa?**

Chưa. Builder base, JDK, Maven/Gradle, dependency resolution và generated build metadata đều ảnh hưởng output. Pin runtime là bước quan trọng nhưng chưa phải end-to-end reproducibility.

**Q9. Image được tải bằng digest có chắc an toàn không?**

Không. Digest xác định nội dung, không bảo đảm nguồn đáng tin, tính hợp pháp hay không có CVE. Cần publisher verification, scan, signatures/attestations và policy.

**Q10. Tôi dùng Kubernetes hỗn hợp AMD64 và ARM64 nên đặt platform ở đâu?**

Xây/push image **multi-platform** rồi dùng digest của index trong deployment; container runtime của từng node chọn variant phù hợp. Chỉ đặt nodeSelector khi cần hạn chế architecture hoặc ứng dụng có dependency native không tương thích.

## 21. Checklist trước khi phát hành Spring Boot image

- [ ] Chọn registry/repository base image đáng tin và Java runtime version được hỗ trợ.
- [ ] Xác nhận tag dự định dùng còn tồn tại, lịch vá bảo mật và OS variant phù hợp.
- [ ] Chạy `docker buildx imagetools inspect` để xem digest ở cấp index/manifest và platform list.
- [ ] Nếu cần multiarch, base image có cả `linux/amd64` và `linux/arm64`.
- [ ] Phân biệt **index digest** với child manifest digest trước khi pin.
- [ ] Release builds dùng pinned base references hoặc lưu nguồn/digest đầy đủ có kiểm soát.
- [ ] Không hardcode `--platform=linux/amd64` trong final FROM khi phát hành ARM64.
- [ ] Build stage `--platform=$BUILDPLATFORM` chỉ dùng khi output Java bytecode thực sự architecture-neutral.
- [ ] Native/JNI libraries được kiểm tra riêng trên mỗi target architecture.
- [ ] Maven/Gradle, JDK, plugins và dependencies được pin/kiểm soát trong CI.
- [ ] Dockerfile dùng multi-stage để không mang compiler/credentials sang runtime.
- [ ] `.dockerignore` loại local secrets/build artifacts không cần.
- [ ] Runtime non-root, network config/permissions/CA certificates đáp ứng ứng dụng.
- [ ] Buildx builder hỗ trợ target platforms; chọn native nodes hoặc QEMU khi hợp lệ.
- [ ] Build/push image đa kiến trúc, inspect output index sau push.
- [ ] Smoke test `GET /ready` trên AMD64 và ARM64 đúng hardware/emulator.
- [ ] Scan cả JRE/OS/Java dependencies; lưu SBOM và provenance khi cần.
- [ ] Deploy bằng **output index digest**, không chỉ mutable tag.
- [ ] Có cơ chế update digest chủ động khi publisher vá CVE, cùng canary/rollback.
- [ ] Ghi lại base digest, application digest, Git commit và test evidence.

## 22. Tài liệu chính thức để đối chiếu

- Docker – [Dockerfile reference: FROM và ARG](https://docs.docker.com/reference/dockerfile/): cú pháp `FROM image:tag@digest`, `--platform` và các automatic build args.
- Docker – [Multi-platform builds](https://docs.docker.com/build/building/multi-platform/): image index/list, emulation, multi-node builders và cross-compilation.
- Docker – [Buildx build --platform](https://docs.docker.com/reference/cli/docker/buildx/build/): xác định platforms đầu ra và registry publish.
- Docker – [Buildx imagetools inspect](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/): đọc image manifests/index, digest và architecture.
- Docker – [Building best practices](https://docs.docker.com/build/building/best-practices/): pin base image digest và quy trình cập nhật/security.
- Docker – [Build variables](https://docs.docker.com/build/building/variables/): `BUILDPLATFORM`, `TARGETPLATFORM` và phạm vi ARG.
- Docker – [FromPlatformFlagConstDisallowed](https://docs.docker.com/reference/build-checks/from-platform-flag-const-disallowed/): tránh cố định architecture trong Dockerfile.
- Docker – [Image inspect](https://docs.docker.com/reference/cli/docker/image/inspect/): image metadata local.
- Docker – [Image digests](https://docs.docker.com/dhi/explore/security-concepts/digests/): digest identities và multi-platform index concepts.
- Spring Boot 3.5 – [Packaging Executable Archives with Maven](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): executable JAR và `repackage`.
- Kubernetes – [Well-Known Labels, Annotations and Taints](https://kubernetes.io/docs/reference/labels-annotations-taints/): `kubernetes.io/os`/`kubernetes.io/arch` cho nodes.

**Ghi nhớ cuối cùng:** **tag** là tên tiện lợi nhưng có thể đổi; **digest** định danh nội dung của **manifest/index** cụ thể; **architecture** quyết định biến thể runtime thực sự. Với Spring Boot Java 17, hãy xác minh base image có đúng `linux/amd64`/`linux/arm64`, build một JAR Java thuần trên toolchain được pin, để final Dockerfile stage chọn target platform của Buildx, publish multi-platform index và **triển khai bằng digest đã được kiểm tra**. Pin cũ không tự nhận bản vá: mọi chiến lược reproducibility phải đi kèm cập nhật, scan và test thường xuyên.