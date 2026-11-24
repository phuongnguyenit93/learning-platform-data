# Giới hạn dùng scratch hoặc distroless khi còn tài nguyên hệ thống cần thiết

## 1. Vì sao image nhỏ nhất chưa chắc là image phù hợp?

Native Image tạo ra executable độc lập với JVM runtime truyền thống, nên có thể đóng gói ứng dụng Spring Boot trong container rất nhỏ. Điều đó khiến các base image như `scratch` hoặc distroless trở nên hấp dẫn: ít package hơn, bề mặt tấn công nhỏ hơn và dung lượng truyền tải thấp hơn.

Tuy nhiên, native executable vẫn có thể phụ thuộc vào thư viện hệ điều hành, CA certificates, timezone database, DNS/NSS, thư mục tạm và các tài nguyên runtime khác. Việc bỏ shell và package manager cũng làm thay đổi cách debug, health check và vận hành. Một image nhỏ nhưng thiếu thư viện hoặc dữ liệu hệ thống có thể khiến ứng dụng không khởi động, không kết nối HTTPS, phân giải DNS sai hoặc xử lý thời gian không đúng.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần chọn base image dựa trên dependency thực tế của executable và yêu cầu vận hành. Bài này giải thích giới hạn của `scratch` và distroless, cách kiểm tra ELF/shared libraries, những tài nguyên hệ thống thường bị bỏ sót, và quy trình xác minh image gần production.

## 2. Phân biệt scratch, distroless và minimal OS image

| Loại image | Đặc điểm | Hệ quả vận hành |
|---|---|---|
| `scratch` | Image rỗng, không có shell, package manager, libc hay CA bundle | Chỉ chạy được binary và file đã copy; mọi dependency phải được cung cấp rõ ràng |
| Distroless | Chỉ chứa một tập runtime files tối thiểu, thường không có shell/package manager | Ít công cụ debug; phải chọn đúng variant và xác minh shared libraries |
| Minimal OS image | Có userspace/package nền tảng nhưng ít package hơn full OS | Dễ bổ sung CA, timezone, libc và công cụ cần thiết hơn |
| Full OS image | Nhiều tiện ích hệ thống | Dễ debug nhưng image lớn và có bề mặt package rộng hơn |

Distroless không phải một image duy nhất. Các variant khác nhau có thể cung cấp libc, CA certificates hoặc thành phần runtime khác nhau. Hãy đọc nội dung và mục đích của đúng tag image đang dùng.

`scratch` không tự cung cấp bất kỳ dependency hệ thống nào. Nếu binary là dynamically linked, chỉ copy binary vào scratch thường không đủ. Nếu binary được link tĩnh, ứng dụng vẫn có thể cần CA certificates, timezone data, file cấu hình hoặc các dữ liệu hệ thống khác.

## 3. Native executable không đồng nghĩa static executable

GraalVM Native Image tạo executable native, nhưng điều đó không có nghĩa binary luôn chứa toàn bộ thư viện hệ điều hành. Tùy toolchain và cách build, executable có thể liên kết động với libc và các shared libraries.

Kiểm tra binary trên Linux:

```bash
file orders-service
ldd orders-service
readelf -l orders-service
readelf -d orders-service
```

- `file` cho biết định dạng, architecture và thông tin ELF cơ bản.
- `ldd` liệt kê shared library dependency trong môi trường phù hợp.
- `readelf -l` giúp kiểm tra ELF program headers, gồm interpreter nếu có.
- `readelf -d` hiển thị dynamic section và dependency entries.

Chỉ chạy `ldd` trên binary đáng tin cậy và trong môi trường an toàn; với artifact không tin cậy, ưu tiên công cụ phân tích ELF tĩnh như `readelf`. Kết quả phụ thuộc môi trường đang kiểm tra: một thư viện có thể được tìm thấy trên host nhưng không tồn tại trong container runtime.

## 4. libc và ABI phải tương thích

Các executable Linux thường phụ thuộc vào một môi trường ABI cụ thể. Ví dụ, binary được build để dùng glibc cần runtime có glibc tương thích. Một image chỉ có musl không tự chạy được binary glibc chỉ vì cả hai đều là Linux.

Các điểm cần xác minh:

- Binary target architecture có khớp node/container host không.
- Executable dùng glibc hay musl.
- Dynamic loader được ghi trong ELF có tồn tại trong image.
- Phiên bản symbol của shared libraries có tương thích.
- Các thư viện bổ sung như `libstdc++`, `libgcc_s` hoặc thư viện native của SDK có được cung cấp không.

Nếu muốn dùng image rất nhỏ, hãy quyết định rõ toolchain/linking strategy từ đầu. Việc chuyển sang musl hoặc static linking có thể yêu cầu builder, native toolchain và cấu hình riêng; không thể chỉ đổi base image ở Dockerfile rồi kỳ vọng binary tự tương thích.

## 5. Scratch và trường hợp binary static

Một executable được link tĩnh có thể giảm số shared library cần có trong runtime image. Tuy nhiên, “static” chỉ mô tả cách liên kết một số thành phần, không có nghĩa toàn bộ nhu cầu runtime đều biến mất.

Ứng dụng vẫn có thể cần:

- CA certificates để xác minh TLS server.
- Timezone database cho xử lý timezone.
- File cấu hình hoặc secret được mount.
- Thư mục ghi tạm hoặc thư mục upload.
- Native library được nạp động.
- DNS/NSS configuration phù hợp.
- User/group identity hoặc file hệ thống mà thư viện kỳ vọng.

Ngoài ra, cách static linking với libc có thể ảnh hưởng tới DNS, name service và cập nhật bảo mật. Cần test hành vi thực tế với resolver/network của môi trường triển khai thay vì chỉ xác nhận lệnh build thành công.

## 6. CA certificates và kết nối HTTPS

Ứng dụng Spring Boot thường gọi HTTPS tới API đối tác, database proxy, identity provider hoặc telemetry collector. TLS cần trust store chứa CA phù hợp.

Nếu base image không có CA bundle, các kết nối HTTPS có thể thất bại với lỗi xác minh certificate, dù DNS và TCP hoạt động bình thường.

Một số hệ thống dùng bundle ở các đường dẫn như:

- `/etc/ssl/certs/ca-certificates.crt`
- `/etc/pki/tls/certs/ca-bundle.crt`

Đường dẫn phụ thuộc distribution. Không hard-code một path nếu ứng dụng phải chạy trên nhiều base image. Có thể cấu hình trust store rõ ràng hoặc copy CA bundle đúng định dạng từ stage phù hợp.

Không tắt certificate verification để “sửa” lỗi thiếu CA. Hãy bổ sung trust roots hợp lệ và kiểm thử HTTPS từ chính container image cuối cùng.

## 7. Timezone database và locale data

Java API có thể xử lý `ZoneId`, `ZonedDateTime`, định dạng ngày giờ và locale. Native executable vẫn cần dữ liệu timezone/locale phù hợp với cách runtime được build và cấu hình.

Nếu thiếu timezone database của hệ điều hành hoặc dữ liệu locale cần thiết, ứng dụng có thể:

- Không nhận diện zone name mong muốn.
- Dùng fallback không phù hợp.
- Định dạng ngày/tháng hoặc số khác với kỳ vọng.
- Có behavior khác giữa local và container.

Không phải mọi API Java đều phụ thuộc trực tiếp vào package `tzdata`; GraalVM/JDK có thể đóng gói hoặc sử dụng dữ liệu theo cơ chế riêng. Cần kiểm tra API thực tế đang dùng, cách Native Image build và runtime base image.

Với nghiệp vụ phụ thuộc múi giờ, dùng zone ID tường minh như `Asia/Ho_Chi_Minh` và kiểm tra trên executable trong image cuối. Đừng chỉ dựa vào timezone mặc định của máy build.

## 8. DNS, NSS và resolver configuration

Ứng dụng container thường gọi service bằng DNS name như `orders-db`, `payment-api` hoặc tên service nội bộ của Kubernetes. Phân giải tên có thể phụ thuộc vào:

- `/etc/resolv.conf`.
- `/etc/hosts`.
- `/etc/nsswitch.conf`.
- libc/resolver implementation.
- DNS search domains và network policy.

Một image scratch không có sẵn các file này, nhưng container runtime/orchestrator có thể mount một số file hệ thống vào container. Cách mount và khả năng resolver phụ thuộc runtime, libc và cách binary được link.

Không giả định DNS hoạt động chỉ vì container có thể mở TCP tới một IP cố định. Test bằng hostname service thực tế trong cùng network namespace và runtime platform dự kiến.

## 9. /tmp, filesystem và quyền ghi

Một số thư viện tạo file tạm, cache, lock hoặc spool file. Các vị trí thường gặp gồm `/tmp`, `/var/tmp` hoặc thư mục được cấu hình riêng.

Scratch không có sẵn các thư mục này. Nếu ứng dụng cần ghi tạm, tạo thư mục trong image hoặc mount volume runtime, đồng thời đặt quyền phù hợp với user chạy process.

Ví dụ Dockerfile:

```dockerfile
FROM scratch
WORKDIR /app
COPY --chown=10001:10001 orders-service /app/orders-service
COPY --chown=10001:10001 --from=certs /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
USER 10001:10001
ENTRYPOINT ["/app/orders-service"]
```

Đây chỉ là minh họa và cần stage `certs` được định nghĩa trong Dockerfile thực tế. Scratch không có `/tmp` mặc định; nếu cần, tạo thư mục trong build stage rồi copy với owner/mode phù hợp, hoặc mount writable volume.

Ưu tiên filesystem read-only cho phần ứng dụng nếu có thể, chỉ cấp writable path cần thiết. Kiểm thử upload, export, temporary file và cleanup bằng đúng UID/GID runtime.

## 10. User, group và identity trong image tối giản

Scratch không chứa `/etc/passwd` hoặc `/etc/group` mặc định. Một số runtime/library có thể tra cứu username, group hoặc home directory qua hệ điều hành. Distroless variant có thể cung cấp user mặc định hoặc metadata khác nhau.

Có thể khai báo numeric UID/GID trong Dockerfile:

```dockerfile
USER 10001:10001
```

Numeric identity giúp không phụ thuộc tên user có trong passwd database, nhưng không tự tạo home directory hay quyền ghi. Hãy kiểm tra:

- File executable có quyền execute cho UID.
- Thư mục làm việc có quyền đọc.
- Writable directory được tạo và sở hữu đúng.
- Volume mount trên Kubernetes có UID/GID phù hợp.
- Thư viện không phụ thuộc việc tra username để tạo path.

Không chạy root chỉ để tránh lỗi permission. Xác định đúng file/path cần quyền và cấp quyền tối thiểu.

## 11. Shell và package manager không có sẵn

Distroless và scratch thường không có `sh`, `bash`, `apt`, `apk` hoặc `yum`. Vì vậy, các thao tác sau thường không dùng được bên trong container:

- `docker exec -it ... sh`
- Cài package sau khi container đã chạy.
- Chạy script shell làm entrypoint.
- Dùng shell form để nối lệnh khởi động.
- Cài công cụ debug trong production container.

Dùng exec-form entrypoint:

```dockerfile
ENTRYPOINT ["/app/orders-service"]
```

Không dùng:

```dockerfile
ENTRYPOINT /app/orders-service
```

Shell form cần shell để thực thi và có thể làm sai tín hiệu dừng process. Với image không có shell, exec form là lựa chọn phù hợp.

Để debug, dùng ephemeral debug container, sidecar/tooling image hoặc chạy binary trong môi trường staging có công cụ cần thiết. Không thêm shell vào production image chỉ để thuận tiện khi kiểm tra thủ công.

## 12. Health check và readiness không phụ thuộc shell

Một số Dockerfile dùng:

```dockerfile
HEALTHCHECK CMD curl -f http://localhost:8080/actuator/health
```

Cách này không hoạt động nếu image không có `curl` hoặc shell. Docker HEALTHCHECK dạng shell command cũng phụ thuộc shell có sẵn trong image.

Các lựa chọn:

- Dùng Kubernetes startup/readiness/liveness probes gọi HTTP trực tiếp từ kubelet.
- Dùng một healthcheck binary nhỏ được đóng gói có chủ đích.
- Dùng cơ chế health check do nền tảng container hỗ trợ mà không cần shell.
- Bỏ Docker HEALTHCHECK nếu orchestrator đã quản lý health probe phù hợp.

Với Spring Boot, cấu hình Actuator health probes và chỉ expose endpoint cần thiết. Readiness nên phản ánh khả năng nhận traffic; liveness nên tránh restart process chỉ vì một dependency tạm thời bị gián đoạn.

## 13. Logging và stdout/stderr

Ứng dụng container nên ghi log ra stdout/stderr để runtime platform thu thập. Không cần cài syslog daemon trong image chỉ để ghi log ứng dụng.

Cần xác minh:

- Logging backend không yêu cầu file path mặc định không tồn tại.
- Log rotation do container platform/agent quản lý.
- Không ghi log vào filesystem read-only nếu không có volume.
- Stack trace có đủ thông tin cần thiết nhưng không làm lộ secret.
- Encoding/locale phù hợp với log collector.

Nếu cần file audit hoặc file output, khai báo volume và retention rõ ràng. Distroless/scratch không cung cấp log rotation tool; đó là trách nhiệm của runtime platform hoặc sidecar/agent.

## 14. Native libraries và các file phụ thuộc lúc chạy

Một số dependency Java gọi native library qua JNI/JNA hoặc thư viện nền tảng. Native executable có thể phụ thuộc thêm `.so` hoặc library khác ngoài binary chính.

Kiểm tra dependency:

```bash
ldd orders-service
readelf -d orders-service
```

Nếu có thư viện được nạp bằng `System.loadLibrary`, tên file và loader path phải hợp lệ trong runtime image. Đảm bảo library đúng architecture, ABI và phiên bản; copy đúng file cùng dependency của nó.

Đừng chỉ kiểm tra `ldd` nếu ứng dụng nạp library động theo tên lúc runtime. Test chính API JNI/JNA từ executable và kiểm tra loader error trong container cuối cùng.

## 15. Distroless có thể là lựa chọn cân bằng

Distroless thường phù hợp khi muốn giảm package nhưng vẫn cần một số thành phần userspace đã chọn. Tuy nhiên, cần chọn đúng variant:

- Variant có glibc/shared libraries phù hợp với executable.
- Variant có CA certificates nếu cần HTTPS.
- Variant có timezone data nếu use case cần.
- Variant phù hợp với architecture và native dependencies.
- User mặc định hoặc cách cấu hình non-root rõ ràng.

Tên tag và nội dung distroless thay đổi theo dự án phát hành. Đọc tài liệu chính thức và kiểm tra image filesystem/manifest; không suy ra nội dung chỉ từ tên `base`, `static` hay `cc`.

Distroless giảm tiện ích debug trong image cuối. Có thể dùng image debug tương ứng cho môi trường troubleshooting, nhưng phải bảo đảm binary và runtime dependencies giống image production.

## 16. Multi-stage build không tự giải quyết runtime dependencies

Multi-stage build giúp không mang compiler, Maven/Gradle cache và source vào runtime image:

```dockerfile
FROM build-image AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -Pnative -DskipTests package

FROM runtime-image
WORKDIR /app
COPY --from=build /workspace/target/orders-service /app/orders-service
USER 10001:10001
ENTRYPOINT ["/app/orders-service"]
```

Ví dụ này chưa chắc đủ cho mọi ứng dụng. Nếu runtime cần CA bundle, timezone data, native library, config hoặc thư mục ghi tạm, phải thêm rõ ràng vào final stage hoặc mount khi chạy.

Builder và runtime phải tương thích về OS, libc, architecture và ABI. Copy binary từ Ubuntu/glibc builder sang scratch hoặc musl-only runtime có thể thất bại dù multi-stage Docker build thành công.

## 17. Kiểm tra image cuối thay vì chỉ kiểm tra build stage

Build Docker image thành công chỉ chứng minh các layer đã được tạo. Cần chạy chính image cuối với các scenario:

1. Khởi động bằng UID/GID production.
2. Xác nhận readiness endpoint hoạt động.
3. Gọi HTTPS endpoint để xác minh CA trust.
4. Gọi service qua DNS name nội bộ.
5. Kiểm tra timezone/locale quan trọng.
6. Thực hiện chức năng cần ghi file tạm.
7. Gọi JNI/native library nếu ứng dụng sử dụng.
8. Gửi SIGTERM và xác nhận shutdown graceful.
9. Kiểm tra log stdout/stderr và exit code.
10. Chạy với filesystem read-only nếu kiến trúc yêu cầu.

Không chạy test trên builder stage rồi suy ra final image hoạt động. Runtime image có thể thiếu file mà builder đã vô tình cung cấp.

## 18. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `exec format error` | Sai architecture hoặc binary format | `file`, target platform và image manifest |
| `No such file or directory` dù binary tồn tại | ELF interpreter/loader không có trong image | `readelf -l`, libc và dynamic loader |
| `error while loading shared libraries` | Thiếu shared library hoặc sai ABI | `ldd`, `readelf -d`, runtime image |
| HTTPS certificate failure | Thiếu CA bundle hoặc trust store sai | CA path và TLS test trong container |
| Không resolve service name | Resolver/NSS/DNS config hoặc network | `resolv.conf`, runtime network, hostname test |
| Lỗi timezone | Thiếu/khác timezone data hoặc default zone | Test ZoneId tường minh và tzdata |
| Permission denied | UID/GID không có quyền file/path | Owner/mode và volume security context |
| Không tạo được file tạm | Thiếu `/tmp` hoặc filesystem read-only | Writable path và temp directory config |
| Docker exec không có shell | Image tối giản theo thiết kế | Debug container hoặc staging tooling |
| Health check luôn fail | Healthcheck gọi curl/shell không có | Dùng orchestrator probe hoặc binary healthcheck |

## 19. Bài thực hành: chọn giữa scratch và distroless

**Bối cảnh:** Order API native cần gọi HTTPS tới payment provider, phân giải DNS service nội bộ, xử lý timezone Việt Nam và ghi file tạm khi xuất hóa đơn.

**Bước 1 — Kiểm tra executable.** Dùng `file`, `readelf` và `ldd` trong builder tương thích để xác định architecture, interpreter và shared library dependencies.

**Bước 2 — Lập runtime dependency inventory.** Ghi libc, CA certificates, DNS/NSS, timezone data, temp directory, native libraries và writable paths.

**Bước 3 — Tạo distroless variant.** Chọn đúng runtime variant có dependency cần thiết, chạy bằng non-root UID và exec-form entrypoint.

**Bước 4 — Tạo scratch variant nếu phù hợp.** Chỉ copy binary và các file được xác định rõ; tạo writable directory nếu cần, bổ sung CA/timezone data theo yêu cầu. Không giả định static binary tự có tất cả dữ liệu hệ thống.

**Bước 5 — Chạy cùng test suite.** Kiểm tra startup/readiness, HTTPS, DNS, timezone, export file, log và graceful shutdown trên từng image.

**Bước 6 — Kiểm tra bảo mật.** Xác nhận non-root, filesystem permissions, package inventory, exposed ports và secret mounts.

**Bước 7 — Đo artifact.** So sánh image size, pull time và chi phí vận hành; ghi rõ cách đo compressed/unpacked layers.

**Bước 8 — Chọn image.** Chọn image nhỏ nhất đáp ứng đầy đủ runtime contract, debug workflow và yêu cầu bảo mật; lưu lại dependency inventory để kiểm tra khi nâng version.

Tiêu chí hoàn thành: dependency hệ điều hành được liệt kê; image cuối khởi động và chạy chức năng thực tế; HTTPS/DNS/timezone/filesystem được kiểm tra; process chạy non-root; lựa chọn base image có số liệu và bằng chứng.

## 20. Kết luận

Scratch và distroless có thể giảm kích thước image và số package, nhưng native executable vẫn cần những thành phần hệ thống phù hợp. libc/loader, shared libraries, CA certificates, DNS/NSS, timezone data, user identity, thư mục tạm, native libraries và công cụ health/debug đều cần được đánh giá theo ứng dụng thực tế.

Hãy kiểm tra ELF và dependency của binary, chọn đúng variant runtime, dùng non-root và exec-form entrypoint, rồi chạy test trên image cuối cùng. Một image tối giản chỉ có giá trị khi vẫn đáp ứng đầy đủ runtime contract: khởi động, kết nối, xử lý dữ liệu, ghi file cần thiết, phát log và shutdown an toàn.
