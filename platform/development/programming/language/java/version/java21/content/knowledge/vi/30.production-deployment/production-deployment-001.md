# Chọn runtime image và bản vá JDK 21 theo chính sách vận hành

Triển khai Java 21 lên production cần chốt rõ ba thứ: **nhà cung cấp JDK**, **runtime image thực sự chạy ứng dụng** và **quy trình cập nhật bản vá**. Nhãn `21` hoặc chữ LTS không đủ để xác định runtime có còn được hỗ trợ, đã nhận security fix hay có phù hợp với chính sách license của tổ chức.

Một image production tốt phải chứa đúng runtime và thư viện hệ điều hành mà ứng dụng cần, có nguồn gốc và phiên bản xác định, chạy với quyền tối thiểu, được quét lỗ hổng và có lịch cập nhật rõ ràng. Image nhỏ hơn có thể giảm bề mặt tấn công, nhưng chỉ nên tối giản sau khi đã kiểm thử đầy đủ TLS, locale, timezone, font, native library, observability và quy trình khắc phục sự cố.

## 1. Phân biệt JDK, runtime image và container image

Ba khái niệm này thường bị gọi chung là “Java image”, nhưng phục vụ các mục đích khác nhau:

| Thành phần | Nội dung | Mục đích |
|---|---|---|
| JDK | Runtime cùng compiler, debugger, công cụ phát triển và các module JDK | Build, test, debug và có thể chạy ứng dụng |
| Runtime image | Bộ runtime Java có các module cần thiết để chạy ứng dụng; có thể là runtime đầy đủ hoặc image tùy chỉnh từ `jlink` | Chạy ứng dụng mà không cần toàn bộ công cụ phát triển |
| Container image | Runtime image hoặc JDK cùng ứng dụng, thư viện hệ điều hành và cấu hình cần thiết trong một OCI image | Đóng gói và triển khai nhất quán trên container platform |

Ứng dụng Java thông thường chỉ cần lệnh `java` để chạy JAR; không cần `javac` trong production. Tuy nhiên, công cụ chẩn đoán như `jcmd`, `jstack`, JFR, shell hoặc package manager có thể cần cho vận hành. Nếu loại bỏ chúng khỏi runtime image, cần có cách debug được kiểm soát, chẳng hạn debug image cùng vendor/JDK build hoặc công cụ attach từ môi trường quản trị.

Không có một lựa chọn runtime duy nhất phù hợp cho mọi hệ thống. Hãy chọn theo khả năng hỗ trợ của vendor, yêu cầu module, native dependency, observability, footprint và quy trình incident response.

## 2. Chọn nhà cung cấp và chính sách hỗ trợ JDK 21

Java 21 là một bản LTS của Java SE, nhưng thời gian hỗ trợ, lịch phát hành binary, điều kiện nhận bản vá và điều khoản sử dụng phụ thuộc nhà cung cấp JDK. LTS không có nghĩa mọi bản phân phối đều có cùng ngày kết thúc hỗ trợ hoặc cùng license.

Khi chọn vendor, cần xác định:

- Ai chịu trách nhiệm phát hành security update và thông báo CVE?
- Runtime có được hỗ trợ trên OS, kiến trúc CPU, container platform và môi trường cloud của tổ chức không?
- Có binary cho đúng hệ điều hành và kiến trúc cần triển khai không?
- Có yêu cầu subscription, support contract, chứng nhận hoặc FIPS provider không?
- Chính sách có cung cấp SBOM, checksum, chữ ký, provenance và hướng dẫn cập nhật không?
- Thời gian hỗ trợ có bao phủ vòng đời ứng dụng và thời gian chuyển sang LTS tiếp theo không?

Ví dụ, Oracle công bố Java 21 là LTS và có các mốc hỗ trợ riêng cho Premier/Extended Support; Adoptium cũng công bố lịch hỗ trợ riêng cho Temurin. Không lấy mốc của Oracle để suy ra mốc hỗ trợ của Temurin, Amazon Corretto, Microsoft Build of OpenJDK hoặc nhà cung cấp khác. Chốt vendor và hợp đồng hỗ trợ trước khi đưa image vào production.

### Theo dõi update stream, không chỉ major version

Một runtime có thể vẫn báo `21` nhưng đã cũ nhiều bản security update. Hãy ghi nhận đầy đủ version string, vendor và build, ví dụ dạng `21.0.x+build`; các nhà cung cấp có thể có hậu tố hoặc cách đóng gói riêng.

Tại thời điểm 16/11/2026, trang release notes của Oracle liệt kê JDK 21.0.13 và các bản build cập nhật liên quan; các tag Temurin 21 cũng đã có bản 21.0.13. Đây chỉ là snapshot để minh họa việc cùng một feature release có nhiều bản phân phối/build. Khi triển khai thật, tra security baseline và release notes mới nhất của đúng vendor ngay trong quy trình phát hành.

**Lưu ý license có tính thời điểm:** Oracle công bố các bản cập nhật Oracle JDK 21 từ tháng 10/2026 chuyển sang điều khoản Java SE OTN; điều kiện sử dụng và quyền phân phối cần được xác nhận theo đúng bản binary và hợp đồng. Không suy luận license chỉ từ việc Java 21 là LTS hoặc từ một image tag trên registry.

## 3. Chọn loại runtime image

### Dùng JDK image cho build, test và chẩn đoán

JDK image phù hợp cho build stage vì cần `javac`, `jdeps`, `jlink`, test runner hoặc công cụ đóng gói. Nó cũng hữu ích cho một môi trường chẩn đoán có kiểm soát khi đội vận hành cần `jcmd`, `jstack`, `jfr` hoặc công cụ khác.

Không nhất thiết phải đưa toàn bộ JDK vào image phục vụ traffic production. Tách build stage và runtime stage giúp image chạy chỉ mang theo ứng dụng cùng runtime cần thiết.

### Dùng JRE/runtime image do vendor cung cấp

Một số vendor cung cấp image `jre` hoặc runtime-only. Đây thường là lựa chọn đơn giản cho ứng dụng không cần compiler và công cụ phát triển lúc chạy. Kiểm tra danh sách module, CA certificates, timezone database, locale, font, native library và khả năng quan sát đi kèm image.

Đừng giả định mọi image có chữ `jre` đều giống nhau. Có vendor cung cấp runtime tối giản, vendor khác đóng gói thêm công cụ hoặc thư viện OS. Đọc tài liệu tag cụ thể và kiểm thử image thực tế.

### Tạo custom runtime bằng jlink

`jlink` ghép các module JDK cùng dependency bắc cầu để tạo runtime image tùy chỉnh. Cách này giảm các module không cần thiết, nhưng đội ứng dụng phải chịu trách nhiệm xác định module, tạo lại image khi JDK có bản vá và kiểm thử sau mỗi lần cập nhật.

Có thể dùng `jdeps` để lấy danh sách module phụ thuộc tĩnh từ artifact:

```bash
# Phân tích dependency module của ứng dụng và thư viện trên classpath.
jdeps --multi-release 21 \
      --class-path 'lib/*' \
      --print-module-deps \
      app.jar
```

Sau khi xem xét output, bổ sung các module được nạp qua reflection, `ServiceLoader`, JDBC driver, logging provider, locale hoặc cơ chế runtime khác mà static analysis không thể xác định đầy đủ. Ví dụ lệnh tạo runtime (danh sách module chỉ mang tính minh họa, phải thay bằng module đã xác minh của ứng dụng):

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging,java.sql,jdk.crypto.ec,jdk.management,jdk.jfr \
  --bind-services \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --output runtime
```

Các điểm cần lưu ý:

- Chạy `jlink` từ đúng JDK 21 distribution/build mà tổ chức đã chọn; dùng module từ cùng JDK image để tránh ghép module khác vendor hoặc khác bản vá.
- `--bind-services` đưa service provider module được tìm thấy cùng dependency của chúng vào image; vẫn phải kiểm tra provider thực tế và các module được nạp động.
- `jdk.jfr`, `jdk.management` hoặc `jdk.jcmd` chỉ thêm khi cách vận hành cần chúng. Image càng nhỏ càng có thể thiếu công cụ chẩn đoán.
- Nếu ứng dụng cần locale ngoài nhóm mặc định, kiểm tra `jdk.localedata` và cấu hình `--include-locales` phù hợp.
- Custom runtime phụ thuộc OS và kiến trúc build. Tạo và kiểm thử image riêng cho Linux/Windows, glibc/musl và từng kiến trúc CPU cần hỗ trợ.
- Mỗi lần cập nhật JDK, phải tạo lại custom runtime từ JDK đã vá; không thể chỉ thay JAR ứng dụng rồi coi runtime cũ đã nhận security fix.

### Chọn theo nhu cầu

| Nhu cầu | Lựa chọn nên đánh giá |
|---|---|
| Muốn vận hành đơn giản, vendor chịu trách nhiệm đóng gói runtime | Vendor JRE/runtime image |
| Ứng dụng cần module hoặc native integration đặc thù | JDK image hoặc custom `jlink` sau khi kiểm thử |
| Cần `jcmd`, JFR, debugger trong môi trường sự cố | JDK image hoặc debug image riêng có kiểm soát |
| Muốn giảm module và footprint, có pipeline kiểm thử/patch runtime | Custom `jlink` image |
| Build Maven/Gradle và chạy ứng dụng trong container | Multi-stage: JDK ở build stage, runtime image ở stage cuối |

## 4. Chọn base OS và kiến trúc container

Base OS là một phần của runtime image và có vòng đời vá lỗi riêng với JDK. Cùng một JDK build có thể được đóng gói trên Ubuntu, Debian, UBI, Alpine hoặc distroless; các biến thể có libc, package và công cụ khác nhau.

Trước khi chọn, kiểm tra:

- **libc:** Alpine thường dùng musl; nhiều native library/JNI binary được build cho glibc. Không đổi sang Alpine chỉ vì image nhỏ nếu chưa xác nhận native compatibility.
- **CPU architecture:** native library phải đúng `amd64`, `arm64` hoặc kiến trúc đích. Kiểm thử trên cùng kiến trúc production, nhất là khi build multi-arch.
- **TLS và CA:** xác nhận truststore Java và CA bundle của OS có đầy đủ root/intermediate CA mà dịch vụ cần. Nếu tổ chức dùng private CA, quản lý cập nhật truststore theo quy trình riêng.
- **Timezone và locale:** kiểm tra tzdata, locale data và định dạng ngày/giờ. JDK update có thể cập nhật IANA timezone database.
- **Font và native dependency:** ứng dụng PDF, image, AWT hoặc thư viện JNI có thể cần fontconfig, font, thư viện native hoặc gói OS bổ sung.
- **Công cụ vận hành:** image tối giản có thể không có shell, package manager, `curl`, `jcmd` hoặc `jfr`. Xác định cách lấy thread dump, heap dump và JFR khi cần.
- **OS lifecycle:** base image phải còn được vendor OS hỗ trợ và nhận bản vá. JDK mới không tự vá OpenSSL, libc, CA bundle hoặc package OS.

Distroless/minimal image giảm thành phần không cần thiết và bề mặt tấn công, nhưng việc thiếu shell/package manager làm thao tác điều tra tại container khó hơn. Có thể dùng một debug image được kiểm soát, cùng JDK vendor/version và cấu hình phù hợp, thay vì cài thêm công cụ vào image production đang chạy.

## 5. Multi-stage Docker build cho Java 21

Mẫu sau minh họa JDK ở build stage và JRE/runtime ở stage cuối. Thay các image reference bằng registry, tag và digest đã được tổ chức phê duyệt; chuỗi digest bên dưới là placeholder, không phải digest có thể dùng trực tiếp.

```dockerfile
# Build stage: dùng JDK 21 để build/test ứng dụng.
FROM registry.example.com/java/temurin:21-jdk@sha256:<approved-build-digest> AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -DskipTests package

# Runtime stage: dùng runtime cùng vendor và update stream đã kiểm thử.
FROM registry.example.com/java/temurin:21-jre@sha256:<approved-runtime-digest> AS runtime
WORKDIR /app
COPY --from=build --chown=10001:10001 /workspace/target/app.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Trong pipeline thực tế:

- Dùng cùng vendor và bản cập nhật tương thích cho build/runtime; nếu khác build, phải có kiểm thử tương thích rõ ràng.
- Không dùng `latest` hoặc tag trôi nổi làm định danh duy nhất cho production artifact.
- Ghim base image bằng digest để build có thể tái lập và audit được. Tự động tạo PR cập nhật digest theo lịch; pin digest mà không cập nhật sẽ giữ cả lỗ hổng cũ.
- Dùng multi-stage để không mang Maven/Gradle cache, source, compiler và build tool vào runtime stage.
- Chạy bằng user không phải root; cấp quyền ghi chỉ cho các thư mục thực sự cần.
- Không đưa password, token, private key hoặc credential vào `ARG`, `ENV`, source hay image layer. Dùng secret manager hoặc runtime secret mount.
- Nếu dùng read-only root filesystem, cấp `tmpfs` hoặc volume riêng cho `/tmp`, log hoặc thư mục ghi được ứng dụng yêu cầu.

## 6. Hardening runtime container

Image đã vá vẫn cần chạy với quyền tối thiểu. Một chính sách container thường xem xét:

- User/group không phải root, UID ổn định và quyền file tối thiểu.
- Bỏ Linux capabilities không cần thiết; bật `no-new-privileges` nếu nền tảng hỗ trợ.
- Read-only root filesystem; chỉ mount writable volume cho dữ liệu thực sự cần lưu.
- Giới hạn CPU, memory, PID và ephemeral storage theo workload đã đo.
- Không chạy SSH daemon, package manager hoặc service không cần trong container ứng dụng.
- Không lưu secret trong image layer hoặc log; hạn chế quyền đọc secret ở runtime.
- Dùng TLS và truststore được quản lý; không tắt certificate validation để sửa lỗi môi trường.
- Cấu hình graceful shutdown và thời gian termination phù hợp để ứng dụng đóng pool, flush dữ liệu và hoàn tất request đang xử lý.

Không đặt một `MaxRAMPercentage` hoặc heap size cố định cho mọi workload. Java 21 nhận biết giới hạn container trong môi trường được hỗ trợ, nhưng cần kiểm tra `MaxRAM`, `MaxHeapSize`, native memory, direct buffer, thread stack và memory limit của orchestrator trong đúng image. Đặt heap quá lớn có thể khiến tổng memory vượt giới hạn container dù heap chưa đầy.

## 7. Chính sách cập nhật bản vá JDK 21

JDK update có thể bao gồm security fixes, bug fixes, cập nhật timezone, CA certificates, crypto implementation và các thay đổi runtime khác. Không nên chỉ cập nhật khi có lỗi ứng dụng; runtime đang production cũng cần theo dõi security baseline của vendor.

Một chính sách vận hành có thể định nghĩa các luồng sau:

| Loại cập nhật | Hành động vận hành |
|---|---|
| Critical/actively exploited vulnerability | Đánh giá ngay mức ảnh hưởng, tạo bản build mới và triển khai theo quy trình khẩn cấp của tổ chức |
| Security CPU/update thường kỳ | Theo dõi advisory của vendor, cập nhật theo SLA nội bộ và không để runtime vượt security baseline |
| Bug fix hoặc regression fix | Đọc release notes, chạy regression/performance test, phát hành theo chu kỳ đã định |
| OS/base image update | Cập nhật riêng base OS, scan lại image và kiểm tra tương thích native library |
| Certificate/timezone data update | Kiểm tra truststore, TLS, lịch, giờ địa phương và các nghiệp vụ phụ thuộc thời gian |

Oracle JDK có lịch Critical Patch Update riêng; các nhà cung cấp OpenJDK khác có lịch build và hỗ trợ riêng. Dùng lịch của đúng vendor và kênh binary đang triển khai. Nếu vendor phát hành bản vá khẩn cấp ngoài chu kỳ, chính sách nội bộ cần có đường xử lý nhanh.

### Không chỉ vá khi đổi tag

Một tag image có thể trỏ tới nội dung khác nhau theo thời gian. Ngược lại, một digest cố định luôn trỏ tới cùng image và sẽ không tự nhận bản vá mới. Vì vậy, quy trình nên là:

1. Theo dõi advisory và bản phát hành mới từ JDK vendor cùng OS vendor.
2. Cập nhật version/tag và digest trong source build.
3. Build lại image, kể cả khi application source không thay đổi.
4. Tạo SBOM và scan CVE cho image mới.
5. Chạy regression, integration, startup, TLS, native, performance và smoke test.
6. Phát hành canary/rolling deployment theo mức rủi ro.
7. Ghi lại digest, JDK version, vendor, OS base và kết quả scan của artifact đã triển khai.

Docker `--pull` giúp lấy metadata/base tag mới khi build, nhưng không thay đổi image nếu Dockerfile ghim một digest cũ. Với digest pinning, phải cập nhật digest trong source và review thay đổi có chủ đích.

## 8. Quản lý SBOM, scan và nguồn gốc image

Một runtime image production nên có thể trả lời được: image được build từ đâu, chứa JDK build nào, package OS nào, dependency ứng dụng nào và ai đã phê duyệt triển khai.

Các bước nên có trong pipeline:

- Sinh SBOM ở định dạng được tổ chức hỗ trợ, chẳng hạn SPDX hoặc CycloneDX.
- Quét lỗ hổng cho cả OS package, JDK và dependency ứng dụng.
- Xác minh checksum/chữ ký hoặc provenance từ nguồn phân phối JDK và base image.
- Ký image hoặc artifact theo hệ thống signing của tổ chức.
- Lưu version string, vendor, build number, base image digest, source revision và thời điểm build.
- Theo dõi CVE mới sau khi image đã phát hành; scan tại build time không đủ cho toàn bộ vòng đời.

Một lỗ hổng có trong package không nhất thiết có thể khai thác trong mọi ứng dụng, nhưng không được tự động bỏ qua chỉ vì package chưa được gọi trong test. Đánh giá mức độ nghiêm trọng, khả năng khai thác, exposure, package path, advisory của vendor và chính sách exception. Exception phải có người sở hữu, lý do, biện pháp giảm thiểu và ngày hết hạn.

Ví dụ với Docker BuildKit có thể xuất SBOM và provenance khi build:

```bash
docker buildx build \
  --pull \
  --sbom=true \
  --provenance=mode=max \
  -t registry.example.com/team/app:release-candidate \
  --push .
```

Lệnh trên minh họa việc tạo metadata build; cần kết hợp scanner, signature/verification và policy gate của registry hoặc CI. Nếu base image được pin digest, hãy cập nhật digest trước khi build để nhận bản vá mới.

## 9. Xác minh runtime thực sự đang chạy

Không chỉ xem Dockerfile hoặc tag để kết luận production đã chạy đúng JDK. Có thể kiểm tra trong container hoặc qua startup diagnostic được bảo vệ:

```bash
java --version
java -XshowSettings:properties -version
```

Ghi nhận tối thiểu:

- `java.runtime.version` và `java.version`.
- `java.vendor` và `java.vm.name`.
- `java.home`.
- OS name/version và `os.arch`.
- Module list nếu đang dùng custom runtime (`java --list-modules`).
- Image digest và base OS release từ metadata của container platform.

Nếu image không có shell hoặc công cụ chẩn đoán, có thể expose thông tin version qua startup log hoặc endpoint quản trị chỉ cho phép truy cập nội bộ. Không công khai thông tin chi tiết runtime, dependency hoặc build metadata ở endpoint không được bảo vệ.

Với custom `jlink` runtime, kiểm tra các module thực sự có mặt:

```bash
./runtime/bin/java --list-modules
./runtime/bin/java --version
```

Sau khi triển khai, xác minh pod/container đang chạy digest dự kiến, không chỉ image tag được khai báo trong manifest. Kiểm tra mọi replica trong rollout để tránh trạng thái một phần chạy JDK mới, một phần vẫn chạy bản cũ ngoài kế hoạch.

## 10. Kiểm thử trước khi đưa bản vá vào production

JDK update thường giữ tương thích Java SE, nhưng có thể thay đổi behavior do security fix, provider, certificate, timezone database, locale data, native library hoặc bug fix. Hãy chạy tối thiểu:

1. **Startup test:** JVM khởi động, load config, module, logging và framework.
2. **Functional regression:** API nghiệp vụ, serialization, database, messaging và scheduled job.
3. **TLS/crypto test:** handshake, certificate chain, truststore, cipher/provider và kết nối dependency.
4. **Time/locale test:** timezone, daylight saving, parsing/formatting và locale được ứng dụng sử dụng.
5. **Native integration:** JNI/FFM, font, PDF/image, compression hoặc thư viện native.
6. **Observability test:** log, metrics, JFR, health check, thread dump/heap dump theo image đã chọn.
7. **Performance test:** startup, throughput, latency p95/p99, memory, GC và thread behavior dưới workload đại diện.
8. **Container test:** user không root, filesystem permissions, signal handling, graceful shutdown, resource limits và architecture đích.

Kiểm thử trên đúng image cuối cùng, không chỉ trên máy developer có JDK đầy đủ. Nếu build stage dùng JDK image khác vendor/patch với runtime stage, test cần chạy bằng runtime stage đó.

## 11. Canary, rollout và rollback

Một bản vá nên được triển khai có kiểm soát:

```text
Build image mới
      |
      v
SBOM + vulnerability scan + signature
      |
      v
Automated tests trên runtime image cuối
      |
      v
Staging / pre-production
      |
      v
Canary một phần traffic
      |
      v
Theo dõi error, latency, CPU, memory, GC, TLS
      |
      +---- Không đạt ----> Dừng rollout, điều tra
      |
      v
Rolling deployment toàn bộ
      |
      v
Xác minh digest và version trên mọi replica
```

Giữ lại digest của bản trước để có thể rollback nhanh khi gặp regression. Tuy nhiên, rollback về image có lỗ hổng bảo mật đã biết có thể tái mở rủi ro. Nếu phải rollback, cần exception có thời hạn, đánh giá exposure và biện pháp giảm thiểu; đồng thời tiếp tục xử lý bản vá thay thế.

Không sửa package trực tiếp bên trong container đang chạy. Tạo image mới đã vá, kiểm thử, ký và triển khai để mọi replica có cùng artifact bất biến. Điều này giúp truy vết và tái lập trạng thái production.

## 12. Ví dụ chính sách vận hành cho một dịch vụ Java 21

Một chính sách nội bộ có thể được mô tả như sau (các thời hạn cụ thể cần được tổ chức phê duyệt theo SLA và mức độ rủi ro):

| Hạng mục | Quy tắc mẫu |
|---|---|
| JDK vendor | Chỉ dùng một distribution đã được phê duyệt và có đầu mối nhận security advisory |
| Feature release | Giữ Java 21 trong thời gian sản phẩm yêu cầu; lập kế hoạch nâng LTS trước khi support window kết thúc |
| Patch level | Theo security baseline mới nhất của vendor; không pin mãi một update cũ |
| Base OS | Dùng OS image còn được hỗ trợ; theo dõi patch OS độc lập với JDK |
| Image identity | Tag dễ đọc cộng digest bất biến; lưu digest đã deploy trong release record |
| Build | Multi-stage; JDK ở build stage, runtime-only/custom runtime ở stage cuối sau kiểm thử |
| Security | Non-root, minimal permissions, SBOM, vulnerability scan và signature/provenance |
| Update cadence | Review mỗi lần vendor phát hành CPU/update và có quy trình khẩn cấp cho critical CVE |
| Validation | Regression, TLS, timezone, native, observability, performance và container tests |
| Rollout | Canary/rolling deployment, theo dõi SLO và rollback có kiểm soát |
| Audit | Ghi vendor, version/build, OS, architecture, SBOM, digest, scan result và approval |

Chính sách này cần gắn với vendor cụ thể. Ví dụ, lịch Oracle CPU, lịch Temurin build và lịch cập nhật base OS có thể khác nhau; một ticket “update Java” không nên chỉ đổi một version string mà bỏ qua OS layer hoặc license review.

## 13. Lỗi vận hành thường gặp

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ứng dụng báo Java 21 nhưng vẫn có CVE cũ | Chỉ ghim major tag, không theo update build hoặc base OS | Kiểm tra version string, digest, vendor advisory và scan image |
| Image nhỏ nhưng lỗi TLS | Thiếu CA certificate, provider hoặc module crypto cần thiết | Kiểm tra truststore, `jdk.crypto.ec`, provider và test handshake |
| Chạy được trên máy build nhưng lỗi trong container | Runtime stage thiếu module, locale, font hoặc native library | Test image cuối cùng trên OS/arch production |
| Custom runtime không chạy một driver | `jdeps` không phát hiện module được nạp qua reflection/service loading | Thêm module cần thiết, xem xét `--bind-services` và chạy integration test |
| JDK đã vá nhưng CVE OS còn nguyên | JDK patch và OS package patch là hai luồng riêng | Rebuild từ base OS đã vá và scan lại toàn image |
| Digest pin khiến image không nhận update | Digest là bất biến; tag mới không thay đổi digest đã ghim | Tự động đề xuất digest mới, review và rebuild định kỳ |
| Không thể lấy thread dump trong production | Runtime image đã loại bỏ công cụ chẩn đoán | Dùng debug image/attach workflow được kiểm soát hoặc giữ module/công cụ cần thiết |
| Rollback khôi phục ứng dụng nhưng tái đưa CVE vào | Bản cũ có lỗ hổng đã biết | Exception có thời hạn, giảm exposure và phát hành bản vá thay thế nhanh |
| Thay vendor JDK gây khác biệt runtime | Provider, crypto, timezone, packaging hoặc support policy khác nhau | Kiểm thử tương thích và phê duyệt vendor migration riêng |

## 14. Checklist chọn và vá runtime image

- [ ] Đã chọn vendor JDK 21 có support lifecycle và kênh security advisory rõ ràng.
- [ ] Đã xác nhận license/redistribution terms của đúng binary và image.
- [ ] Đã chọn JDK, vendor JRE/runtime image hoặc custom `jlink` theo nhu cầu vận hành.
- [ ] Đã xác minh module, TLS provider, CA, locale, timezone, font và native library.
- [ ] Đã chọn base OS còn được hỗ trợ và đúng libc/CPU architecture.
- [ ] Đã tách build stage và runtime stage nếu không cần compiler trong production.
- [ ] Đã pin base image digest và có automation tạo PR cập nhật digest.
- [ ] Đã có quy trình vá OS layer và JDK layer riêng.
- [ ] Đã tạo SBOM, scan CVE, xác minh nguồn gốc và ký artifact theo policy.
- [ ] Container chạy non-root, quyền tối thiểu và không chứa secret trong image layer.
- [ ] Đã kiểm tra memory/CPU limit và JVM ergonomics trong container.
- [ ] Đã kiểm thử image cuối trên đúng runtime, OS và architecture production.
- [ ] Có quy trình canary, xác minh digest trên mọi replica và rollback có kiểm soát.
- [ ] Đã lưu version, vendor, build, base image, digest, scan result và approval.

## Tài liệu tham khảo

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): trạng thái LTS và mốc hỗ trợ theo sản phẩm Oracle.
- [Oracle JDK 21 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/21all-relnotes.html): update/build JDK 21, security baseline và khuyến nghị cập nhật theo CPU.
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/): binary JDK 21 hiện hành và điều khoản license theo bản phát hành.
- [Eclipse Temurin Support](https://adoptium.net/support/): lịch hỗ trợ và update stream riêng của Temurin.
- [Eclipse Temurin Container Images](https://adoptium.net/installation/containers): tag JDK/JRE, base OS và kiến trúc image.
- [The jlink Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): tạo custom runtime image từ module và dependency bắc cầu; trách nhiệm cập nhật image thuộc về nhà phát triển.
- [The jdeps Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): `--print-module-deps` để lấy module dependency cho `jlink`.
- [Docker Build Best Practices](https://docs.docker.com/build/building/best-practices/): pin base image version/digest và quy trình cập nhật base image.
- [Docker Build: Find and Fix Vulnerabilities](https://docs.docker.com/learn/content/find-and-fix-vulnerabilities-before-you-ship/): build với SBOM và provenance, cập nhật digest đã pin.
