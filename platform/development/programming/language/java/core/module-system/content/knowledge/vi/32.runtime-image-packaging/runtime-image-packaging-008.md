# Kiểm thử image trên môi trường triển khai

## 1. Vì sao phải kiểm thử runtime image ở môi trường triển khai?

Khi đóng gói ứng dụng modular bằng \`jlink\`, dự án tạo ra một runtime image chứa JVM và tập hợp các module cần thiết. Khi triển khai bằng container hoặc máy chủ, ứng dụng thường chạy từ image này thay vì dùng JDK đầy đủ của máy phát triển.

Build thành công chưa chứng minh image có thể chạy trong production. Môi trường triển khai có thể khác máy build về hệ điều hành, kiến trúc CPU, thư viện native, user chạy process, quyền truy cập filesystem, biến môi trường, chứng thư TLS, DNS, timezone và cấu hình mạng.

Một image có thể khởi động trên máy developer nhưng thất bại trong container vì:

- Runtime image được tạo cho hệ điều hành hoặc kiến trúc CPU khác.
- Thiếu JDK module do cấu hình \`jlink\` chưa bao gồm dependency cần thiết.
- Provider service không được liên kết vào image.
- Ứng dụng vẫn tham chiếu file hoặc executable chỉ tồn tại trên máy build.
- User production không có quyền đọc file cấu hình, ghi thư mục tạm hoặc mở cổng.
- Base image thiếu thư viện native hoặc chứng thư CA mà ứng dụng cần.
- Runtime flags, environment variables hoặc working directory khác với môi trường đã thử nghiệm.

Vì vậy, cần kiểm thử chính artifact sẽ được phát hành, trong môi trường gần với production nhất có thể. Không chỉ chạy test bằng JDK của máy build rồi suy luận rằng runtime image cũng hoạt động.

## 2. Phân biệt các loại artifact cần kiểm thử

Trong quy trình packaging modular, thường có ba loại artifact:

| Artifact | Nội dung | Điều cần xác nhận |
| --- | --- | --- |
| Modular JAR | Bytecode ứng dụng và \`module-info.class\` | Module descriptor, dependency và service declarations đúng. |
| Runtime image | JVM cùng các module được liên kết bởi \`jlink\` | Image có đủ module, chạy được trên nền tảng mục tiêu và không phụ thuộc JDK bên ngoài. |
| Container image | Runtime image hoặc JRE cùng ứng dụng, cấu hình và filesystem của container | Process chạy được với base image, user, network, mount và giới hạn tài nguyên thực tế. |

Nếu dùng \`jpackage\`, native application package còn có launcher, metadata và cấu trúc cài đặt theo hệ điều hành. Cần kiểm thử package được cài đặt và chạy như người dùng production, không chỉ chạy file JAR bên trong.

Một kiểm thử có giá trị phải sử dụng đúng artifact cuối. Ví dụ, nếu production chạy container được build từ runtime image thì nên kiểm thử container đó. Nếu chỉ chạy thư mục \`build/runtime-image\` trên máy developer, các khác biệt của container vẫn chưa được kiểm tra.

## 3. Xác định nền tảng mục tiêu trước khi tạo image

Runtime image do \`jlink\` tạo ra phụ thuộc vào nền tảng JDK dùng để tạo nó. Không nên coi image là một gói Java có thể sao chép tùy ý giữa Linux, Windows, macOS hoặc giữa các kiến trúc CPU khác nhau.

Trước khi build, ghi nhận:

- Hệ điều hành và phiên bản hoặc base distribution.
- Kiến trúc CPU, ví dụ x86_64 hoặc AArch64.
- Phiên bản JDK và vendor dùng để compile, link.
- Base container image và phiên bản/digest nếu triển khai bằng Docker.
- Các thư viện native hoặc executable bên ngoài mà ứng dụng cần.
- User/group, working directory và filesystem mount trong production.

Nếu production chạy Linux container trên một distribution cụ thể, hãy build và test image trong môi trường Linux tương thích. Một image được tạo trên Windows không thể mang nguyên trạng sang Linux chỉ vì cả hai đều dùng Java 21.

Đối với Linux, khác biệt giữa các bản phân phối còn có thể liên quan tới glibc, OpenSSL, font, timezone data và các thư viện native khác. Đối với ứng dụng có JNI/JNA, driver native hoặc thư viện tính toán native, kiểm tra cả kiến trúc và ABI của thư viện.

## 4. Tạo runtime image có thể kiểm thử

Ví dụ ứng dụng modular có main module là \`com.acme.app\`, các module phụ thuộc nằm trong thư mục \`mods\`. Dùng JDK 21 để tạo image:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --bind-services \
  --launcher app=com.acme.app/com.acme.app.Main \
  --output build/runtime-image
~~~

Giải thích:

- \`--module-path\` cung cấp các module JDK và module ứng dụng cho linker.
- \`--add-modules\` chọn module gốc để resolve dependency graph.
- \`--bind-services\` yêu cầu linker xem xét các service provider có thể được liên kết từ các module quan sát được.
- \`--launcher\` tạo launcher có tên \`app\` trỏ đến main class của module.
- \`--output\` là thư mục runtime image được tạo.

Nếu ứng dụng dùng service provider qua JPMS, cần xác nhận consumer có khai báo \`uses\` và provider có \`provides\` trong descriptor. \`--bind-services\` không thể tự sửa một descriptor sai hoặc thêm provider JAR không nằm trong module path.

Có thể dùng các tùy chọn như \`--strip-debug\`, \`--no-header-files\`, \`--no-man-pages\` hoặc \`--compress\` để giảm kích thước image. Chỉ áp dụng sau khi đã xác định cấu hình cần thiết và có kiểm thử chứng minh ứng dụng vẫn hoạt động. Tối ưu kích thước không nên làm mất dữ liệu hoặc thành phần runtime mà ứng dụng cần.

## 5. Kiểm tra nội dung runtime image

Sau khi link thành công, kiểm tra image trước khi chạy ứng dụng.

### 5.1. Kiểm tra Java executable và phiên bản

Trên Linux/macOS:

~~~bash
build/runtime-image/bin/java -version
build/runtime-image/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
build/runtime-image/bin/java.exe -version
build/runtime-image/bin/java.exe --list-modules
~~~

Luôn gọi executable bằng đường dẫn trong image. Nếu chỉ gõ \`java -version\`, shell có thể gọi JDK trên máy build hoặc một Java khác trong PATH, khiến kết quả kiểm thử không phản ánh image.

Kiểm tra:

- Runtime có phiên bản Java dự kiến.
- Các module ứng dụng được liên kết nếu chọn đóng gói application modules vào image.
- Các module JDK cần thiết có mặt.
- Module service provider cần thiết được liên kết khi sử dụng service binding.
- Image không vô tình dựa vào một JDK đầy đủ được cài sẵn trên máy kiểm thử.

### 5.2. Kiểm tra module graph và service binding

Có thể dùng:

~~~bash
build/runtime-image/bin/java --list-modules
~~~

để xem các module trong runtime image.

Khi cần chẩn đoán service provider, đối chiếu module consumer có \`uses\` và provider có \`provides\`. Nếu image cần provider nhưng module đó không có trong runtime image, xem lại module path và \`--bind-services\` hoặc tập module được chỉ định bằng \`--add-modules\`.

Nếu ứng dụng được phát hành dưới dạng JAR riêng thay vì được link vào image, kiểm tra module resolution bằng chính runtime image:

~~~bash
build/runtime-image/bin/java \
  --show-module-resolution \
  --module-path app/mods \
  --module com.acme.app/com.acme.app.Main
~~~

Không sử dụng JDK bên ngoài để chạy lệnh kiểm tra này. Mục tiêu là xác nhận runtime đã link có thể resolve và chạy đúng module graph của ứng dụng.

### 5.3. Kiểm tra module descriptor của ứng dụng

Dùng JDK tooling phù hợp để xem descriptor của modular JAR:

~~~bash
jar --describe-module --file app/mods/com.acme.app.jar
~~~

Nếu cần kiểm tra dependency tới JDK modules, có thể dùng:

~~~bash
jdeps --print-module-deps --module-path app/mods app/mods/com.acme.app.jar
~~~

Kết quả giúp đối chiếu tập module cần thiết với runtime image. Công cụ phân tích static có thể không phát hiện đầy đủ dependency được sử dụng qua reflection, JNI, resource hoặc tên class được cấu hình động. Những đường đi này phải được kiểm tra bằng integration test trong môi trường thực tế.

## 6. Smoke test bằng chính runtime image

Smoke test nên xác nhận image có thể khởi động ứng dụng và thực hiện một luồng chức năng tối thiểu. Không chỉ kiểm tra process có exit code 0; một server có thể khởi động rồi dừng ngay do lỗi cấu hình, hoặc chạy nhưng không phục vụ được request.

Ví dụ chạy launcher đã tạo bởi \`jlink\`:

~~~bash
build/runtime-image/bin/app
~~~

Hoặc chạy module trực tiếp:

~~~bash
build/runtime-image/bin/java \
  --module com.acme.app/com.acme.app.Main
~~~

Nếu application module không được link vào image mà được phân phối riêng:

~~~bash
build/runtime-image/bin/java \
  --module-path app/mods \
  --module com.acme.app/com.acme.app.Main
~~~

Smoke test nên kiểm tra ít nhất:

1. Process khởi động bằng đúng Java executable trong image.
2. Module graph resolve thành công.
3. Application đọc được cấu hình bắt buộc.
4. Các service provider cần thiết được phát hiện và khởi tạo.
5. Ứng dụng có thể thực hiện một thao tác nghiệp vụ tối thiểu.
6. Server có thể bind vào địa chỉ/cổng dự kiến nếu ứng dụng là service.
7. Health endpoint hoặc readiness signal trả về trạng thái sẵn sàng.
8. Process dừng đúng cách khi nhận tín hiệu shutdown.

Nếu ứng dụng chạy nền, hãy kiểm tra readiness thay vì chỉ chờ process tồn tại. Đối với HTTP service, gửi request thực tế đến endpoint health hoặc một endpoint nghiệp vụ nhỏ sau khi server đã bind.

## 7. Kiểm thử container giống production

Nếu runtime image được đưa vào Docker, hãy build và chạy container từ đúng Dockerfile và base image dự kiến phát hành.

Ví dụ Dockerfile tối giản:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/runtime-image /opt/app

RUN useradd --system --uid 10001 appuser \
    && chown -R appuser:appuser /opt/app /app

USER 10001:10001

ENTRYPOINT ["/opt/app/bin/app"]
~~~

Đây chỉ là ví dụ cho Linux image có công cụ \`useradd\`. Một số base image tối giản hoặc distroless không có shell và user management command; khi đó tạo user ở bước build khác hoặc dùng user đã được cung cấp bởi base image.

Build và chạy:

~~~bash
docker build -t acme-app:test .
docker run --rm --name acme-app-test -p 8080:8080 acme-app:test
~~~

Trong môi trường test, xác nhận:

- Container dùng đúng base image và runtime artifact.
- Process chạy bằng user không đặc quyền giống production.
- Working directory đúng.
- Port được publish hoặc expose theo cấu hình.
- Environment variables và mounted configuration có đủ.
- Process có quyền đọc application files và ghi đúng thư mục được phép.
- Container không dựa vào JDK của host.
- Health check và shutdown hoạt động.

Không chạy container bằng root chỉ để làm mất lỗi permission. Nếu production dùng non-root user, test cũng cần dùng non-root user để phát hiện sớm các file hoặc thư mục bị sở hữu sai.

### 7.1. Read-only filesystem và thư mục tạm

Nhiều môi trường triển khai mount filesystem read-only để giảm khả năng thay đổi runtime artifact. Nếu ứng dụng cần ghi file, phải xác định rõ thư mục nào được phép ghi, ví dụ thư mục tạm hoặc volume dữ liệu.

Có thể chạy thử với filesystem read-only:

~~~bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 8080:8080 \
  acme-app:test
~~~

Điều chỉnh mount theo ứng dụng. Không phải mọi ứng dụng đều có thể chạy với filesystem read-only ngay lập tức; mục tiêu là phát hiện chính xác đường dẫn ghi file và cấp quyền tối thiểu cần thiết.

Kiểm tra log, upload, cache, PID file, temporary file và thư mục chứa dữ liệu. Nếu ứng dụng cần ghi dữ liệu bền vững, dùng volume được quản lý thay vì ghi vào thư mục cài đặt runtime.

### 7.2. Giới hạn tài nguyên và tín hiệu dừng

Container production có thể có giới hạn CPU, memory và PID. Kiểm thử trong giới hạn tương tự giúp phát hiện lỗi cấp phát bộ nhớ, timeout, pool thread hoặc thời gian khởi động.

Ví dụ:

~~~bash
docker run --rm \
  --memory=512m \
  --cpus=1 \
  -p 8080:8080 \
  acme-app:test
~~~

Nếu dùng JVM trong container, kiểm tra heap sizing và memory headroom trong giới hạn container. Heap không phải toàn bộ memory usage: metaspace, code cache, direct buffers, thread stacks và native libraries cũng tiêu thụ bộ nhớ.

Gửi tín hiệu dừng theo cách môi trường production sử dụng và xác nhận ứng dụng đóng connection, flush dữ liệu cần thiết và thoát trong thời hạn grace period.

## 8. Kiểm thử cấu hình hệ điều hành và dịch vụ bên ngoài

Runtime image chỉ cung cấp Java runtime và các module được liên kết. Nó không tự đóng gói mọi thành phần hệ điều hành mà ứng dụng cần.

Các hạng mục nên kiểm thử trong container hoặc máy triển khai:

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| DNS và network | Có thể phân giải hostname và kết nối tới dịch vụ cần thiết. |
| TLS/CA certificates | HTTPS và kết nối TLS tin cậy chứng thư của môi trường. |
| Timezone | Thời gian hiển thị, lịch chạy và timestamp phù hợp cấu hình production. |
| Locale | Định dạng số, ngày tháng, encoding và thông báo phù hợp. |
| Native libraries | JNI/JNA và thư viện hệ thống được nạp đúng phiên bản/kiến trúc. |
| Font | Chức năng tạo PDF, ảnh hoặc render văn bản có font cần thiết. |
| Proxy | JVM và ứng dụng nhận đúng cấu hình proxy nếu môi trường yêu cầu. |
| File permissions | User runtime đọc được secret/config và ghi được các thư mục đã cấp quyền. |

Nếu ứng dụng dùng \`java.time\`, \`Locale\` hoặc TLS, đừng chỉ kiểm tra JVM khởi động. Hãy thực hiện một request hoặc test thực sự đi qua các chức năng đó.

Đối với ứng dụng dùng JDBC, kiểm tra driver có mặt, kết nối tới database, xác thực và thực hiện một truy vấn nhỏ. Đối với messaging hoặc object storage, kiểm tra kết nối và một thao tác tối thiểu có thể quan sát được.

## 9. Kiểm thử service provider và reflection trong image

Việc chạy trên JDK đầy đủ có thể vô tình che giấu lỗi do thiếu provider module hoặc cấu hình mở package. Runtime image tối giản giúp bộc lộ các vấn đề này.

Nếu dùng \`ServiceLoader\`, hãy thực hiện luồng thực tế để xác nhận provider được phát hiện. Nếu provider được khai báo bằng JPMS, kiểm tra \`uses\`, \`provides\` và việc liên kết module bằng \`jlink --bind-services\`. Nếu ứng dụng chạy plugin trong \`ModuleLayer\` riêng, hãy kiểm thử đúng layer và đúng overload \`ServiceLoader.load(layer, service)\`.

Nếu framework cần deep reflection, xác nhận các package được mở bằng descriptor \`opens\` hoặc JVM option \`--add-opens\` trong đúng lệnh khởi chạy. Một flag chỉ được cấu hình cho test JVM không tự động áp dụng cho container production.

Nếu module cần truy cập public type trong package chưa export, kiểm tra \`exports\` hoặc \`--add-exports\`. Đừng dùng \`opens\` để thay thế public API access, và đừng thêm flag rộng chỉ để làm image chạy được mà không xác định module/package thực sự cần quyền.

## 10. Kiểm thử đúng artifact sau mỗi lần thay đổi

Một thay đổi trong module descriptor, dependency graph, service provider, JDK version hoặc Docker base image có thể làm thay đổi runtime image. Vì vậy, test cần chạy trên artifact được tạo bởi đúng build đang chuẩn bị phát hành.

Quy trình đề xuất:

1. Build modular JAR và kiểm tra module descriptor.
2. Tạo runtime image bằng đúng JDK/toolchain và module path của build.
3. Kiểm tra danh sách module bằng \`bin/java --list-modules\` trong image.
4. Chạy smoke test bằng Java executable hoặc launcher bên trong image.
5. Build container từ đúng runtime image.
6. Chạy container bằng user, environment, volume và resource limits giống production.
7. Gửi request health và một vài request nghiệp vụ đại diện.
8. Kiểm tra log, exit code, readiness, provider discovery và shutdown.
9. Lưu lại image digest, JDK version, base image digest và kết quả kiểm thử gắn với artifact đã test.

Không dùng một thư mục runtime image cũ để test sau khi source hoặc dependency đã thay đổi. Hãy bảo đảm build output được tạo lại theo quy trình CI của commit đang phát hành.

## 11. Kiểm thử trên nền tảng đích

Nếu production triển khai trên nhiều nền tảng hoặc kiến trúc, cần tạo và kiểm thử runtime image tương ứng cho từng target. Một image Linux x86_64 không đại diện cho Linux ARM64, Windows hoặc macOS.

Có thể tổ chức matrix CI theo:

- OS và phiên bản base image.
- CPU architecture.
- JDK vendor/version.
- Loại package (runtime image, container hoặc native installer).
- Profile cấu hình production.

Với mỗi target, thực hiện ít nhất smoke test và kiểm tra các native dependency quan trọng. Nếu không có runner thật cho kiến trúc đích, emulator hoặc cross-build chỉ là bằng chứng một phần; cần có kiểm thử trên môi trường target trước khi phát hành chính thức.

Đặc biệt, không kiểm thử container chỉ trên host Linux rồi giả định mọi runtime environment tương đương. Distribution, libc, certificate store và user policy có thể khác nhau.

## 12. Chẩn đoán lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Image không có executable java | Runtime image chưa được tạo đúng hoặc copy thiếu thư mục | Kiểm tra cấu trúc output và Docker COPY path. |
| \`UnsupportedClassVersionError\` | Bytecode được compile bằng phiên bản mới hơn runtime | Đối chiếu \`javac --release\`, JDK compile và runtime version. |
| \`FindException\` hoặc module not found | Thiếu module trong module path hoặc image | Kiểm tra descriptor, \`--list-modules\`, \`--module-path\` và \`jlink --add-modules\`. |
| \`ServiceConfigurationError\` hoặc không có provider | Service descriptor/provider không được resolve hoặc liên kết | Kiểm tra \`uses\`, \`provides\`, \`--bind-services\` và module layer. |
| \`InaccessibleObjectException\` | Package chưa mở cho deep reflection | Kiểm tra \`opens\` hoặc \`--add-opens\` trong JVM thực tế. |
| \`UnsatisfiedLinkError\` | Thiếu native library, sai kiến trúc hoặc sai ABI | Kiểm tra thư viện native trong base image và target architecture. |
| TLS handshake hoặc certificate error | CA store hoặc cấu hình TLS thiếu | Kiểm tra trust store, certificate mount và cấu hình JVM. |
| Không ghi được file | User hoặc filesystem không có quyền ghi | Kiểm tra UID/GID, ownership, mount và thư mục tạm. |
| Container khởi động rồi thoát | Main process kết thúc hoặc startup failure | Đọc log, exit code và cấu hình ENTRYPOINT/CMD. |
| Health check thất bại dù process còn chạy | App chưa sẵn sàng, sai port hoặc health endpoint | Kiểm tra readiness, bind address và container health command. |
| Chạy trên máy dev nhưng lỗi production | Môi trường, biến cấu hình hoặc dependency hệ điều hành khác | Chạy đúng container/base image và user production. |

Khi có lỗi, giữ lại log đầy đủ và lệnh khởi chạy thực tế. Tránh sửa bằng cách thêm module hoặc mở package hàng loạt trước khi biết lỗi thuộc dependency, module access, filesystem hay OS runtime.

## 13. Checklist trước khi phát hành runtime image

- [ ] Đã xác định OS, architecture, JDK và base image mục tiêu.
- [ ] Runtime image được tạo từ đúng module graph và toolchain.
- [ ] Đã kiểm tra \`bin/java --version\` và \`--list-modules\` của image.
- [ ] Các service provider cần thiết được resolve và khởi tạo.
- [ ] Ứng dụng khởi động bằng executable bên trong image.
- [ ] Smoke test và health/readiness test thành công.
- [ ] Container chạy bằng user không đặc quyền.
- [ ] Quyền đọc config/secret và quyền ghi thư mục tạm đã được kiểm tra.
- [ ] DNS, network, TLS, timezone và native dependencies cần thiết đã được thử.
- [ ] Shutdown và giới hạn tài nguyên đã được thử.
- [ ] Đã test trên nền tảng đích hoặc có bằng chứng rõ về giới hạn của môi trường kiểm thử.
- [ ] Image digest và kết quả kiểm thử được gắn với artifact chuẩn bị phát hành.

Kiểm thử runtime image phải chứng minh rằng chính artifact được phát hành có thể chạy trong điều kiện triển khai dự kiến. Kết hợp kiểm tra module graph, smoke test, container integration test và nền tảng đích sẽ giúp phát hiện sớm lỗi packaging mà unit test trên JDK đầy đủ thường không nhìn thấy.
