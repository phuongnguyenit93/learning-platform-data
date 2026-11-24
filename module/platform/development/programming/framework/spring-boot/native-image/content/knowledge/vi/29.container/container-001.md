# Container image chứa native executable khác với container chạy JAR

Spring Boot có thể được đóng gói trong container theo hai cách phổ biến: chạy **executable JAR trên JVM** hoặc chạy **native executable đã biên dịch bằng GraalVM Native Image**. Cả hai đều có thể được phát hành dưới dạng OCI container image và triển khai bằng Docker, Kubernetes hoặc nền tảng tương thích. Tuy nhiên, nội dung image, runtime dependency, cách khởi động, yêu cầu build và cách chẩn đoán khác nhau đáng kể.

Container chạy JAR cần một Java Runtime Environment (JRE) để thực thi bytecode. Container native chạy một file thực thi theo kiến trúc và hệ điều hành mục tiêu; nó không cần JVM để chạy ứng dụng, nhưng vẫn có thể cần libc, dynamic loader, shared libraries, CA certificates, timezone data và các file runtime khác.

Bài học này so sánh hai kiểu image, hướng dẫn tạo image bằng Cloud Native Buildpacks và Docker multi-stage, chọn runtime base image, xử lý glibc/musl, cấu hình user và filesystem, quản lý signal/health check, kiểm thử image cuối và đưa artifact vào CI/CD.

## 1. Phân biệt JAR container và native container

Một JAR là bytecode Java cùng dependency. Container chạy JAR thường khởi động Java runtime rồi truyền JAR cho lệnh `java -jar app.jar`. Một native executable là mã máy được tạo trước cho target OS/CPU; container khởi chạy trực tiếp file đó.

| Thành phần | Container chạy executable JAR | Container chạy Native Image |
|---|---|---|
| Entry point | `java -jar app.jar` | `./application` |
| Runtime chính | JRE | Native executable và GraalVM Native Image runtime được liên kết vào binary |
| JVM trong image | Có | Không cần JVM |
| Artifact ứng dụng | JAR/bytecode | Binary native theo OS/architecture |
| Tính di động của artifact | JAR thường dùng được trên nhiều OS/CPU có JRE phù hợp | Binary phải khớp OS, architecture và ABI |
| Thời điểm biên dịch | Bytecode được JVM thực thi/JIT khi chạy | AOT trước khi phát hành |
| Reflection/dynamic access | JVM thường hỗ trợ linh hoạt | Cần metadata hoặc cơ chế AOT phù hợp |
| Thư viện hệ thống | JRE và native dependency của thư viện | libc, loader, shared libraries và JNI dependency nếu có |
| Khởi động | Phải khởi tạo JVM và Spring context | Thường nhanh hơn, nhưng vẫn phụ thuộc Spring context và dependency |
| Chẩn đoán | Bộ công cụ JVM/HotSpot tùy runtime | Các tính năng Native Image được chọn khi build và công cụ OS |

Cần tránh một nhầm lẫn: **container native không có nghĩa binary luôn được liên kết tĩnh**. GraalVM Native Image mặc định thường tạo binary liên kết động. Nó có thể cần glibc và các shared libraries trong run image. Muốn tạo executable fully static phải chọn cấu hình và toolchain phù hợp, thường dùng musl trên Linux.

## 2. Container image thực sự chứa những gì?

OCI image là một tập layer filesystem cùng metadata mô tả cách khởi chạy container. Runtime image có thể bao gồm:

- Executable hoặc JAR của ứng dụng.
- JRE nếu ứng dụng chạy bytecode.
- libc, dynamic loader và shared libraries nếu binary cần.
- CA certificate để gọi HTTPS.
- Timezone database nếu ứng dụng xử lý múi giờ.
- File cấu hình, template hoặc resource ngoài classpath.
- User/group, thư mục làm việc và quyền filesystem.
- Image configuration: entrypoint, command, environment, exposed ports và labels.

Sơ đồ khái quát:

~~~mermaid
flowchart TB
    subgraph JVM["Container chạy JAR"]
      A["OCI image"] --> B["Linux runtime base"]
      B --> C["JRE"]
      C --> D["Spring Boot executable JAR"]
      D --> E["java -jar"]
    end
    subgraph NATIVE["Container chạy Native Image"]
      F["OCI image"] --> G["Linux runtime base"]
      G --> H["libc / loader / shared libs nếu cần"]
      H --> I["Spring Boot native executable"]
      I --> J["Chạy trực tiếp"]
    end
~~~

Image native có thể bỏ JRE nên thường giảm số thành phần runtime. Tuy vậy, kích thước cuối còn phụ thuộc binary, base image, shared libraries, certificate, timezone và resource. Không thể kết luận image native luôn nhỏ hơn image JAR nếu chưa đo cùng ứng dụng và cùng yêu cầu runtime.

## 3. Khi nào chọn JAR image, khi nào chọn native image?

Container JAR phù hợp khi cần giữ pipeline Java hiện tại, phụ thuộc thư viện chưa hỗ trợ Native Image, cần plugin/runtime class loading linh hoạt hoặc muốn cùng một artifact chạy trên nhiều kiến trúc có JRE.

Container native phù hợp khi startup time, mật độ triển khai, footprint hoặc việc chạy trong môi trường không có JVM là yêu cầu quan trọng, và ứng dụng cùng dependency đã tương thích AOT.

| Tiêu chí | JAR container | Native container |
|---|---|---|
| Tốc độ build | Thường nhanh hơn | Native compilation có thể lâu và cần nhiều RAM/CPU |
| Startup | Có bước khởi động JVM | Thường nhanh hơn |
| Peak throughput | Có thể hưởng lợi từ JIT sau warm-up | Có thể khác tùy workload và profile |
| Memory | Có overhead JVM; phụ thuộc GC và cấu hình | Không có JVM heap theo mô hình HotSpot; vẫn có Java heap và native memory của Native Image |
| Thư viện dynamic | Linh hoạt hơn | Cần kiểm tra metadata/AOT và runtime feature |
| Debugging | Hệ sinh thái JVM rộng | Phụ thuộc các tính năng chẩn đoán đã build |
| Artifact đa nền tảng | JAR thường dùng lại được | Build riêng theo target |
| Phù hợp | Ứng dụng tổng quát, plugin động, dependency khó chuyển đổi | Service đã xác minh native compatibility, cần startup/footprint tốt |

Không chọn native chỉ vì image có vẻ nhỏ. Hãy đo startup, memory, throughput, build time, chi phí CI và độ phức tạp vận hành trên workload thật.

## 4. Hai đường tạo native container image

Spring Boot hỗ trợ hai cách chính:

1. **Cloud Native Buildpacks (CNB):** Maven hoặc Gradle gọi Spring Boot plugin để biến ứng dụng thành OCI image. Buildpack thực hiện các bước build và tạo run image.
2. **Docker multi-stage:** một stage có GraalVM/native-image compiler tạo executable; stage cuối chỉ chứa binary và runtime dependency cần thiết.

Buildpacks giảm lượng Dockerfile phải tự quản lý và có thể tạo layer/SBOM theo buildpack. Multi-stage Dockerfile cho phép kiểm soát rõ builder, runtime base, package hệ thống và filesystem cuối.

~~~mermaid
flowchart TD
    A["Source + Spring AOT"] --> B{"Chọn cách đóng gói"}
    B --> C["Cloud Native Buildpacks"]
    B --> D["Docker multi-stage"]
    C --> E["Builder image + buildpacks"]
    E --> F["Native executable"]
    F --> G["Run image + app layers"]
    D --> H["GraalVM builder stage"]
    H --> I["Native executable"]
    I --> J["Runtime base image"]
    J --> K["OCI image"]
    G --> L["Test final image"]
    K --> L
~~~

Dù chọn cách nào, cần test image cuối cùng. Một binary chạy được trong builder chưa chứng minh nó chạy được trong run image.

## 5. Yêu cầu build và tương thích phiên bản

Native container image phụ thuộc vào các phiên bản phối hợp:

- Spring Boot và Spring Framework.
- JDK/GraalVM Native Image.
- GraalVM Native Build Tools.
- Cloud Native Buildpacks builder và buildpack.
- Run image, libc và shared libraries.
- OS và CPU architecture mục tiêu.

Với tài liệu Spring Boot 4.2.0 hiện hành, hướng dẫn Buildpacks yêu cầu build bằng ít nhất JDK 25 vì Buildpacks sử dụng phiên bản GraalVM Native Image tương ứng với Java version dùng để biên dịch. Các dòng Spring Boot trước đó có baseline và cấu hình khác; không áp yêu cầu JDK 25 cho mọi dự án. Hãy đối chiếu hướng dẫn đúng Spring Boot release đang dùng.

Native Image không hỗ trợ cross-compilation theo cách có thể lấy một binary Linux x86-64 rồi đổi thành ARM64 sau build. Cần build trên target tương ứng hoặc dùng builder/runner thực thi đúng kiến trúc.

## 6. Tạo native image bằng Spring Boot Buildpacks với Maven

Để Maven tạo native container image, dự án thường cần Spring Boot parent và GraalVM Native Build Tools plugin. Parent Spring Boot cung cấp profile `native` với các bước AOT/native cần thiết.

Phần plugin trong `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Build image:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Spring Boot plugin gọi Cloud Native Buildpacks để tạo image chứa native executable. Image có tên mặc định theo artifact/version của ứng dụng; có thể cấu hình tên image và builder/run image trong phần cấu hình plugin.

Nếu không dùng `spring-boot-starter-parent`, phải tự cấu hình các execution cần thiết, bao gồm Spring AOT `process-aot` và Native Build Tools goal tương ứng. Không chỉ bật `BP_NATIVE_IMAGE=true` rồi kỳ vọng một JAR chưa có AOT assets tự biến thành native executable.

## 7. Tạo native image bằng Spring Boot Buildpacks với Gradle

Gradle cần áp dụng Spring Boot plugin và GraalVM Native Image plugin:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
    id("org.graalvm.buildtools.native") version "0.11.2"
}
~~~

Các version ở đây chỉ minh họa một bộ phiên bản cụ thể; hãy dùng version tương thích với Spring Boot/JDK mà dự án đang pin và tránh nâng riêng plugin ngoài kiểm soát.

Khi `org.graalvm.buildtools.native` được áp dụng, Spring Boot Gradle plugin tự cấu hình AOT tasks và `bootBuildImage` tạo native image:

~~~bash
./gradlew bootBuildImage
~~~

Có thể cấu hình tên image và run image trong task `bootBuildImage` theo Spring Boot Gradle plugin. Kiểm tra log build để xác nhận buildpack đã chọn native executable thay vì JVM launch mode.

## 8. Dùng pack CLI với JAR đã xử lý AOT

Có tình huống pipeline build JAR trước, sau đó một bước khác tạo native image. JAR phải chứa generated classes và JSON hints do Spring AOT tạo ra.

Với Cloud Native Buildpacks CLI:

~~~bash
pack build orders-service:native \
  --builder paketobuildpacks/ubuntu-resolute-builder \
  --run-image paketobuildpacks/ubuntu-resolute-run-tiny \
  --path target/orders-service.jar \
  --env BP_NATIVE_IMAGE=true
~~~

`BP_NATIVE_IMAGE=true` là biến môi trường dành cho quá trình buildpack build. Nó yêu cầu buildpack tạo native executable từ JAR AOT. Không nhầm biến này với biến runtime mà ứng dụng đọc khi container chạy.

Trong hướng dẫn Spring Boot 4.2.0, ví dụ `pack` dùng JDK 25 trở lên và builder/run image Ubuntu Resolute tương ứng. Builder và run image cần tương thích với nhau. Tên/tag ví dụ có thể thay đổi theo release của Paketo; nên pin version hoặc digest thay vì để `latest` trong pipeline production.

## 9. Builder image và run image có vai trò khác nhau

Cloud Native Buildpacks tách môi trường build khỏi môi trường chạy:

| Thành phần | Builder image | Run image |
|---|---|---|
| Mục đích | Detect/build, chạy buildpack, compiler và công cụ native | Cung cấp nền tảng chạy ứng dụng |
| GraalVM/native-image | Có trong build environment khi native build cần | Không cần compiler |
| Maven/Gradle/build tools | Có thể được cung cấp trong build stage | Không cần |
| Shell và debug tools | Thường có nhiều công cụ hơn | Có thể bị lược bỏ |
| Package build-time | Không cần đưa tất cả vào final image | Chỉ chứa runtime package cần thiết |
| Dùng production | Không | Có |

Một lỗi thường gặp là copy cả builder image thành runtime image. Điều đó làm image cuối lớn, tăng số package và bề mặt tấn công. Run image chỉ nên chứa thành phần cần để chạy binary.

Spring Boot 4.2.0 hiện dùng Paketo Ubuntu Resolute builder và run image tiny theo cấu hình mặc định trong hướng dẫn. Run image tiny có footprint và attack surface thấp, không có shell và chỉ có tập system library rút gọn. Nếu cần công cụ chẩn đoán hoặc package bổ sung, có thể chọn run image đầy đủ hơn hoặc dùng debug image riêng.

## 10. Container chạy JAR bằng Dockerfile

Một Dockerfile đơn giản cho JVM image:

~~~dockerfile
FROM eclipse-temurin:25-jre

WORKDIR /app

COPY --chown=10001:10001 target/orders-service.jar /app/app.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Image này cần JRE để chạy bytecode. Trong pipeline thực tế, có thể dùng multi-stage build để compile/package JAR trong stage Maven/Gradle rồi chỉ copy JAR vào JRE runtime stage.

Không cần đưa JDK, Maven, Gradle hoặc source code vào runtime image. Chọn JRE major version tương thích với bytecode và framework của ứng dụng.

## 11. Container chạy native executable bằng Docker multi-stage

Ví dụ dưới đây dùng GraalVM Community Native Image container làm build stage và Debian slim làm runtime stage. Dự án cần có Maven Wrapper và profile `native` đã cấu hình.

~~~dockerfile
FROM ghcr.io/graalvm/native-image-community:25i4 AS native-build

WORKDIR /workspace

COPY . .

RUN chmod +x mvnw
RUN ./mvnw -Pnative -DskipTests native:compile

FROM debian:bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata zlib1g libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=native-build --chown=10001:10001 \
    /workspace/target/orders-service \
    /app/application

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["/app/application"]
~~~

Điều chỉnh:

- Tag GraalVM phải khớp JDK/GraalVM mà dự án hỗ trợ; pin tag cụ thể hoặc digest.
- Đường dẫn `/workspace/target/orders-service` phải khớp tên executable do Maven tạo.
- Runtime package trong ví dụ là điểm khởi đầu; kiểm tra `readelf`/`ldd` trên binary và cài đúng shared libraries mà ứng dụng thực sự cần.
- Nếu dùng JNI, copy JNI library cùng dependency bắc cầu và cấu hình loader search path.
- Nếu ứng dụng cần font, CA riêng, timezone, template hoặc file ngoài, đưa chúng vào runtime image hoặc mount khi chạy.
- Dùng `.dockerignore` để tránh copy `target`, `.git`, file secret và artifact không cần thiết vào build context.

Không phải dự án nào cũng cần đúng các package `zlib1g` hoặc `libstdc++6`; dependency thực tế phụ thuộc binary, toolchain và thư viện native. Hãy xác minh bằng công cụ của target image.

## 12. Vì sao Docker multi-stage hữu ích?

Multi-stage build tách công cụ biên dịch khỏi runtime:

~~~mermaid
flowchart LR
    A["Source code + wrapper"] --> B["Builder stage"]
    B --> C["Spring AOT"]
    C --> D["GraalVM native-image"]
    D --> E["Executable"]
    E --> F["Copy binary"]
    F --> G["Runtime stage"]
    G --> H["Non-root container"]
~~~

Lợi ích:

- Không mang compiler và build tools vào production.
- Giảm dung lượng và số package runtime.
- Dễ kiểm soát libc, CA, timezone và shared libraries.
- Có thể cache build stage độc lập với runtime layer.
- Dễ scan và review thành phần thực sự được phát hành.

Tuy nhiên, multi-stage không tự làm binary tương thích. Nếu builder tạo binary cần glibc mới hơn runtime stage, container vẫn không chạy. Builder và runtime phải được chọn dựa trên ABI thực tế.

## 13. Native executable mặc định không nhất thiết là static

Native Image mặc định thường tạo executable liên kết động. Binary có thể yêu cầu dynamic loader và các thư viện như libc hoặc zlib tùy cấu hình. Việc image không chứa JRE không có nghĩa image có thể chỉ chứa mỗi file binary.

Có ba kiểu liên kết cần phân biệt:

| Kiểu | Cách liên kết | Base image thường phù hợp |
|---|---|---|
| Dynamic | Liên kết động với libc và các shared libraries cần thiết | Run image có đúng loader/libc/shared libraries |
| Mostly static | Liên kết tĩnh các thư viện native trừ libc | Image glibc-based như Debian/Ubuntu hoặc distroless Debian |
| Fully static | Liên kết tĩnh với musl trên Linux | Có thể chạy trong `scratch` nếu không cần file runtime ngoài |

GraalVM hỗ trợ build fully static trên Linux với musl toolchain. Static linking với glibc không được hỗ trợ theo tài liệu Native Image. Cấu hình ví dụ:

~~~text
--static
--libc=musl
~~~

Đây là hai build option cần truyền cho Native Image builder; với Spring Boot executable JAR, hãy để Spring Boot/Native Build Tools cung cấp AOT assets và argument file phù hợp thay vì mặc định gọi `native-image -jar` trực tiếp trên mọi fat JAR. Với Native Build Tools, truyền các tùy chọn tương ứng vào build arguments nếu toolchain hỗ trợ. Việc tạo static executable phụ thuộc OS/architecture và musl toolchain; không giả định mọi GraalVM distribution đều cung cấp cùng khả năng.

## 14. Chọn glibc, musl, distroless và scratch

Một số lựa chọn phổ biến:

- **Debian/Ubuntu slim:** dùng khi binary liên kết động với glibc và cần package runtime được chọn lọc.
- **Distroless Debian:** phù hợp với binary mostly-static hoặc binary đã được xác minh có đủ shared library; thường không có shell/package manager.
- **Alpine:** dùng musl; binary glibc không tự động tương thích.
- **Scratch:** filesystem gần như trống; chỉ phù hợp khi binary và các file bắt buộc đã được cung cấp đầy đủ, thường với fully static executable.

GraalVM có tùy chọn mostly-static `--static-nolibc`: liên kết tĩnh các thư viện liên quan nhưng giữ libc động. Cấu hình này có thể phù hợp với runtime glibc-based và distroless Debian.

Fully static không có nghĩa ứng dụng không cần file hệ thống. HTTPS vẫn cần CA certificates; timezone có thể cần tzdata; ứng dụng có thể cần config, font hoặc resource ngoài. Nếu dùng `scratch`, phải copy các file này và đảm bảo đường dẫn đúng.

## 15. OS và CPU architecture của image native

Native executable gắn với target cụ thể:

| Binary | Runtime cần tương thích |
|---|---|
| Linux x86-64 | Linux AMD64 và ABI tương ứng |
| Linux AArch64 | Linux ARM64 và ABI tương ứng |
| macOS ARM64 | macOS ARM64 |
| Windows x64 | Windows x64 |

Một binary Linux không chạy trực tiếp trên Windows chỉ vì được copy vào Windows container. Tương tự, binary build trên macOS không phải Linux executable cho Docker Linux container.

Đối với image multi-architecture:

1. Tạo native executable riêng cho từng target.
2. Build final image trên runner hoặc builder đúng kiến trúc.
3. Kiểm tra image manifest có đủ platform.
4. Chạy smoke test trên từng architecture.
5. Gắn digest/manifest đã được kiểm thử vào release.

Buildx và QEMU có thể hỗ trợ một số workflow đa kiến trúc, nhưng không biến Native Image thành cross-compiler. Native compilation trong môi trường giả lập có thể chậm hoặc gặp giới hạn; ưu tiên runner native hoặc builder từ xa cho từng kiến trúc.

## 16. Cấu hình runtime và secrets

Container nên nhận cấu hình môi trường khi chạy thay vì đóng cứng trong image:

~~~bash
docker run --rm \
  --publish 8080:8080 \
  --env SPRING_PROFILES_ACTIVE=production \
  --env SERVER_PORT=8080 \
  --env SPRING_DATASOURCE_URL=jdbc:postgresql://db:5432/orders \
  orders-service:native
~~~

Tên biến môi trường Spring Boot thường dùng dạng uppercase và dấu gạch dưới. Các biến trên là ví dụ; không đưa password thật vào command line hoặc image layer.

Các nguyên tắc:

- Dùng secret manager hoặc secret mount của nền tảng triển khai.
- Không đưa password, token, private key vào Dockerfile `ARG` hoặc `ENV` khi build.
- Mount file cấu hình bên ngoài khi cần.
- Giữ cùng một image cho nhiều môi trường và thay đổi config khi chạy.
- Đặt `SPRING_PROFILES_ACTIVE` rõ ràng.
- Xác nhận biến môi trường không làm lộ thông tin nhạy cảm trong inspect/log.

Build-time environment như `BP_NATIVE_IMAGE` điều khiển buildpack; runtime environment như `SPRING_PROFILES_ACTIVE` điều khiển ứng dụng. Hai nhóm có vòng đời khác nhau.

## 17. User non-root và quyền filesystem

Image native không nên mặc định chạy bằng root. Chọn UID/GID cố định hoặc user do base image cung cấp:

~~~dockerfile
COPY --from=native-build --chown=10001:10001 \
    /workspace/target/orders-service \
    /app/application

USER 10001:10001
~~~

Kiểm tra:

- Binary có quyền execute.
- Config, CA certificate và resource có quyền đọc.
- Ứng dụng chỉ ghi vào volume hoặc thư mục được cấp quyền.
- `/tmp` có tồn tại và writable nếu thư viện tạo file tạm.
- Log đi ra stdout/stderr thay vì ghi vào file không có volume.
- Không giả định process có quyền bind port thấp hoặc thay đổi system setting.

Có thể thử read-only root filesystem:

~~~bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --user 10001:10001 \
  --publish 8080:8080 \
  orders-service:native
~~~

Nếu ứng dụng cần ghi upload hoặc dữ liệu, mount volume riêng và cấp quyền cụ thể. `--read-only` là một cấu hình kiểm thử/hardening; cần xác định trước các thư mục ứng dụng được phép ghi.

## 18. ENTRYPOINT, signal và graceful shutdown

Nên dùng exec form cho entrypoint:

~~~dockerfile
ENTRYPOINT ["/app/application"]
~~~

Exec form giúp executable nhận signal từ container runtime trực tiếp hơn. Nếu dùng shell form như `ENTRYPOINT /app/application`, shell có thể trở thành process trung gian và làm việc chuyển tiếp signal khó dự đoán.

Khi triển khai:

- Kiểm tra ứng dụng xử lý `SIGTERM` và chạy shutdown hooks.
- Cấu hình thời gian grace period đủ để hoàn tất request và đóng connection.
- Không dùng `docker kill` như cách dừng bình thường; `docker stop` gửi SIGTERM trước rồi mới SIGKILL khi hết timeout.
- Kiểm tra connection pool, message consumer và scheduler được đóng đúng cách.
- Với Kubernetes, cấu hình `terminationGracePeriodSeconds` và readiness để ngừng nhận traffic trước khi process kết thúc.

Native executable vẫn có lifecycle của ứng dụng Java/Spring. Việc không có JVM không làm mất nhu cầu graceful shutdown.

## 19. Port, EXPOSE, health check và readiness

`EXPOSE 8080` trong Dockerfile chỉ ghi metadata về cổng dự kiến; nó không publish port ra host. Khi chạy local cần map cổng:

~~~bash
docker run --rm -p 8080:8080 orders-service:native
~~~

Nếu dùng Spring Boot Actuator, có thể expose readiness/liveness endpoint và cấu hình probe của Kubernetes. Cần phân biệt:

- **Liveness:** process có còn hoạt động không?
- **Readiness:** ứng dụng có thể nhận traffic nghiệp vụ không?
- **Startup probe:** ứng dụng đã hoàn tất khởi động chưa?

Không viết `HEALTHCHECK` gọi `curl` trong image tiny/distroless nếu image không chứa curl hoặc shell. Có thể dùng health probe của orchestrator gọi HTTP endpoint từ bên ngoài container. Nếu bắt buộc dùng Docker HEALTHCHECK, phải chủ động đưa health client phù hợp vào image hoặc dùng cơ chế kiểm tra không cần shell có sẵn.

## 20. So sánh kích thước, startup và memory đúng cách

Khi so sánh JAR image với native image, cần giữ các điều kiện như nhau:

- Cùng commit và chức năng ứng dụng.
- Cùng OS/architecture và môi trường chạy.
- Cùng cấu hình Spring profile và dependency.
- Cùng workload, số request và thời gian đo.
- Cùng giới hạn CPU/memory của container.
- Cùng chính sách logging, TLS và health probe.

Ghi nhận ít nhất:

| Chỉ số | Cách đo |
|---|---|
| Image size | Kích thước OCI image và tổng layer |
| Build time | Thời gian tạo JAR/native binary và final image |
| Startup time | Từ khi process bắt đầu đến readiness |
| Memory | RSS/cgroup memory và heap metrics phù hợp |
| CPU | CPU trong startup và steady state |
| Throughput | Request/second trên workload xác định |
| Latency | p50/p95/p99 và error rate |
| Operational cost | Build cache, registry storage, debug và patch cycle |

Native thường khởi động nhanh, nhưng build lâu hơn. Image native không nhất thiết luôn nhỏ hơn vì binary có thể lớn, base image cần thêm package hoặc ứng dụng cần JNI/resource. Native Image cũng có thể giữ một số vùng memory khác với JVM; so sánh RSS và cgroup thay vì chỉ so sánh heap.

## 21. Layer caching và build reproducibility

Native compilation thường tốn tài nguyên. Cần tận dụng cache nhưng tránh làm cache che khuất artifact cũ:

- Dùng Docker BuildKit cache mount cho Maven/Gradle dependency cache nếu tự quản lý Dockerfile.
- Tận dụng cache của Cloud Native Buildpacks.
- Pin GraalVM builder, buildpack và run image.
- Pin dependency version và plugin version.
- Ghi lại build args, OS, architecture và toolchain.
- Build lại khi cập nhật base image hoặc native dependency.
- Không dùng tag `latest` làm tham chiếu duy nhất trong release.

Với Dockerfile, `.dockerignore` nên loại `target`, `build`, `.git`, IDE files và secret không cần cho build context. Chỉ copy các file cần thiết ở từng stage để cải thiện cache.

Native executable gắn với toolchain và target; để có thể tái tạo, cần lưu metadata build và image digest cùng artifact.

## 22. Bảo mật và chuỗi cung ứng của container

Native image có thể giảm thành phần runtime vì không cần JRE, nhưng không tự động làm image an toàn. Vẫn cần quản lý package hệ điều hành, thư viện native, certificate, config và quyền process.

Checklist bảo mật:

- Dùng base image nhỏ, được duy trì và có lịch cập nhật.
- Chạy non-root.
- Không đưa compiler, package manager hoặc debug tools vào runtime nếu không cần.
- Không lưu secrets trong image.
- Scan final image và các package OS.
- Lưu SBOM và image digest.
- Ký image theo quy trình phát hành của tổ chức.
- Giới hạn Linux capabilities và dùng security profile phù hợp.
- Theo dõi CVE của cả base image và native dependencies.
- Có quy trình rebuild image khi base image hoặc GraalVM được cập nhật.

Buildpacks có thể cung cấp metadata/layers/SBOM theo builder và buildpack được chọn. Với Dockerfile tự viết, pipeline cần chủ động tạo SBOM và scan image cuối. Hãy scan cả runtime image, không chỉ source dependency hoặc executable.

## 23. Debug container native khi không có shell

Run image tiny hoặc distroless có thể không có shell, package manager, `ps`, `curl` hoặc `ldd`. Điều đó không có nghĩa container không thể chẩn đoán.

Bắt đầu từ bên ngoài:

~~~bash
docker inspect orders-service-native
docker logs orders-service-native
docker image inspect orders-service:native
docker history orders-service:native
~~~

Nếu container thoát ngay, xem exit code và log. Kiểm tra command/entrypoint, environment, port, permission và mount.

Để điều tra binary:

- Dùng builder/debug image tương thích để chạy `file`, `readelf` hoặc `ldd`.
- Kiểm tra ELF interpreter và shared library dependency.
- Dùng debug image tương ứng với run image để xác minh package runtime.
- Chạy một container chẩn đoán riêng với cùng filesystem và libraries.
- Không thêm shell vào production image chỉ để debug nếu có thể dùng debug variant.

Một lỗi `No such file or directory` dù binary tồn tại có thể do dynamic loader trong ELF header không có ở runtime image. `Exec format error` thường liên quan đến OS/architecture không khớp. `libxyz.so not found` cho biết thiếu shared library hoặc loader search path.

## 24. Thực hành: tạo hai image từ cùng một ứng dụng Spring Boot

Giả sử có service tên `orders-service`, dùng Spring MVC và có endpoint `GET /actuator/health`.

### Bước 1 — Tạo JAR image

Đóng gói JAR bằng Maven:

~~~bash
./mvnw package
~~~

Dockerfile JVM:

~~~dockerfile
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --chown=10001:10001 target/orders-service.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Build và chạy:

~~~bash
docker build -f Dockerfile.jvm -t orders-service:jvm .
docker run --rm -p 8080:8080 orders-service:jvm
~~~

### Bước 2 — Tạo native image bằng Buildpacks

Với Maven đã cấu hình native profile:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Hoặc Gradle đã áp dụng GraalVM Native Image plugin:

~~~bash
./gradlew bootBuildImage
~~~

Ghi lại tên image được plugin tạo ra và xác minh image metadata.

### Bước 3 — Hoặc tạo native executable bằng Docker multi-stage

Dùng Dockerfile multi-stage ở mục 11. Đảm bảo Maven Wrapper, profile native, GraalVM version và runtime base image tương thích. Build cho đúng OS/architecture mục tiêu.

### Bước 4 — Kiểm tra image

~~~bash
docker image inspect orders-service:jvm
docker image inspect orders-service:native
docker history orders-service:jvm
docker history orders-service:native
~~~

Ghi lại image size, layer, base image, architecture và entrypoint. Không chỉ so sánh số MB; cần kiểm tra cả package và runtime dependency.

### Bước 5 — Chạy smoke test

~~~bash
curl --fail http://localhost:8080/actuator/health
~~~

Gửi request nghiệp vụ thực, kiểm tra response và logs. Với native image, kiểm thử thêm reflection, JSON serialization, resource, JNI và các integration path mà ứng dụng sử dụng.

### Bước 6 — So sánh và ghi kết quả

| Hạng mục | JAR image | Native image |
|---|---|---|
| Runtime command | `java -jar` | Executable trực tiếp |
| JRE trong image | Có | Không |
| Build time | Ghi nhận | Ghi nhận native compile riêng |
| Image size | Đo thực tế | Đo thực tế |
| Startup/readiness | Đo cùng điều kiện | Đo cùng điều kiện |
| Memory/CPU | Đo cùng workload | Đo cùng workload |
| Shared libraries | JRE và native deps | Native executable và native deps |
| Tính tương thích | Kiểm tra JRE/dependency | Kiểm tra OS/arch/ABI/hints |

## 25. Lỗi thường gặp khi đóng gói

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Image vẫn chạy JAR dù muốn native | Chưa áp dụng GraalVM Native Image plugin hoặc chưa bật native build | Kiểm tra Maven profile/Gradle plugin và log Buildpacks |
| Buildpack báo thiếu AOT assets | JAR chưa được xử lý Spring AOT | Chạy AOT processing và đóng gói generated assets vào JAR |
| Binary không chạy trong container | Sai OS/architecture hoặc thiếu loader | Build đúng target, kiểm tra ELF/PE/Mach-O |
| `GLIBC_x.y not found` | Runtime glibc cũ hơn binary yêu cầu | Dùng run image tương thích hoặc build trên base phù hợp |
| `libxyz.so not found` | Thiếu shared library | Kiểm tra `ldd` và cài package cần thiết |
| Container thoát ngay | Entrypoint sai, permission hoặc native startup error | Kiểm tra inspect, exit code và logs |
| Không ghi được file | Chạy non-root nhưng thư mục không writable | Sửa ownership hoặc mount volume |
| Health check luôn fail | Endpoint chưa expose hoặc image thiếu curl/shell | Dùng orchestrator probe hoặc thêm health client có chủ đích |
| Native image gọi HTTPS lỗi | Thiếu CA bundle hoặc truststore | Cung cấp CA phù hợp và test HTTPS |
| Image ARM64 chạy trên AMD64 không được | Binary được build cho sai kiến trúc | Build riêng từng target |
| `scratch` chạy nhưng HTTPS lỗi | Thiếu CA certificate | Copy CA bundle hoặc dùng runtime base phù hợp |
| Container không graceful shutdown | Signal không đến executable hoặc shutdown timeout quá ngắn | Dùng exec-form entrypoint và test SIGTERM |

## 26. Checklist trước khi phát hành

- [ ] Xác định image chạy JAR hay native executable.
- [ ] Pin Spring Boot, JDK/GraalVM, Native Build Tools, builder và run image.
- [ ] Xác nhận AOT assets có trong JAR nếu dùng buildpack chuyển JAR.
- [ ] Xác nhận native binary đúng OS, architecture và ABI.
- [ ] Kiểm tra glibc/musl và shared library dependency.
- [ ] Chọn run image chỉ chứa runtime package cần thiết.
- [ ] Cung cấp CA, timezone, resource và JNI library nếu cần.
- [ ] Dùng non-root user và cấp quyền filesystem tối thiểu.
- [ ] Dùng exec-form entrypoint và kiểm tra SIGTERM/graceful shutdown.
- [ ] Cấu hình readiness/liveness đúng với dependency.
- [ ] Kiểm thử chính final image, không chỉ builder stage.
- [ ] Chạy black-box smoke test và integration test.
- [ ] Scan image, lưu SBOM, digest và build metadata.
- [ ] Kiểm thử từng architecture được phát hành.
- [ ] Đo image size, startup, memory và throughput trên cùng workload.

## 27. Ghi nhớ

Container chạy JAR mang theo JRE và thực thi bytecode bằng `java -jar`. Container chạy Native Image khởi chạy executable đã biên dịch, không cần JVM nhưng vẫn phải thỏa OS, architecture, ABI và các runtime dependency của binary. Cả hai đều là OCI image; sự khác biệt nằm ở nội dung và cách process được khởi chạy.

Spring Boot có thể tạo native container image qua Cloud Native Buildpacks hoặc kết hợp GraalVM Native Image builder với Docker multi-stage. Buildpacks quản lý builder/run image và các layer; Dockerfile multi-stage cho phép kiểm soát trực tiếp runtime filesystem. Dù chọn cách nào, phải test final image, dùng non-root, cấu hình signal/health probe và cung cấp đúng shared libraries/resource.

Native executable mặc định không đồng nghĩa fully static. Binary liên kết động cần libc và shared libraries; fully static trên Linux thường dùng musl, còn mostly-static vẫn cần libc. Hãy chọn base image dựa trên dependency thực tế, build riêng cho từng kiến trúc và phát hành đúng image digest đã được kiểm thử.

### Tài liệu tham khảo

- Spring Boot — Developing Your First GraalVM Native Application: https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Container Images: https://docs.spring.io/spring-boot/reference/packaging/container-images/
- GraalVM — Containerize a Native Executable and Run in a Container: https://www.graalvm.org/dev/reference-manual/native-image/guides/containerise-native-executable-and-run-in-docker-container/
- GraalVM — Build Static or Mostly-Static Native Executables: https://www.graalvm.org/latest/reference-manual/native-image/guides/build-static-executables/
- GraalVM Community Container Images: https://www.graalvm.org/latest/getting-started/container-images/
- Cloud Native Buildpacks — Buildpacks: https://buildpacks.io/docs/

Tên builder/run image, buildpack environment và yêu cầu JDK phụ thuộc Spring Boot/Paketo version. Hãy dùng tài liệu đúng release và pin image tag hoặc digest trong pipeline.
