# Chẩn đoán lỗi Docker daemon, Buildpacks, kiến trúc image và quyền tệp

Khi tạo hoặc chạy Spring Boot container image bằng **Cloud Native Buildpacks (CNB)**, một lỗi nhìn giống “Docker build lỗi” có thể xuất phát từ nhiều tầng: Docker client không kết nối được daemon; daemon không pull được builder/run image; buildpack không detect hoặc build được ứng dụng; image được tạo cho kiến trúc CPU khác; hoặc process non-root không đọc/ghi được tệp và volume.

Muốn sửa đúng, trước tiên phải xác định lỗi xảy ra ở **giai đoạn nào và do thành phần nào trả về**. Bài này hướng dẫn chẩn đoán từ Docker Engine, Spring Boot Maven/Gradle plugin, CNB lifecycle, image platform đến UID/GID và filesystem permissions.

Ví dụ dùng Spring Boot 3.3, Java 17 và image giả định `registry.example.com/team/diagnostic-app:1.0.0`. Các lệnh shell dùng Linux/macOS trừ khi ghi rõ Windows/PowerShell. Ưu tiên lệnh đọc trạng thái trước khi thay đổi cấu hình.

## 1. Xác định lỗi thuộc tầng nào

Luồng tạo và chạy image:

```text
Maven / Gradle command
        |
        v
Spring Boot build plugin
        |
        v
Docker client configuration
(context, host, TLS, socket)
        |
        v
Docker daemon / Engine
        |
        +------------------------------+
        |                              |
        v                              v
Pull CNB builder image           Pull CNB run image
        |                              |
        +---------------+--------------+
                        |
                        v
               CNB lifecycle + buildpacks
              analyze -> detect -> restore
                    -> build -> export
                        |
                        v
               OCI application image
                        |
                        v
             Docker daemon / registry
                        |
                        v
                  Container runtime
                        |
                        v
          Process user + filesystem + mounts
                        |
                        v
                Spring Boot application
```

| Dấu hiệu | Tầng cần điều tra đầu tiên |
| --- | --- |
| `Cannot connect to the Docker daemon` | Docker daemon, context, socket, network |
| `permission denied ... docker.sock` | Quyền truy cập Docker socket |
| `failed to pull builder/run image` | Registry auth, DNS, TLS, network |
| `no buildpack groups passed detection` | Source artifact, builder và buildpack detection |
| `failed to launch` | Launch process, run image, application configuration |
| `no space left on device` | Disk/inodes/cache của Docker host |
| `no matching manifest` | Image architecture/platform |
| `exec format error` | Binary/script không đúng kiến trúc hoặc định dạng |
| `Permission denied` khi app chạy | User, file mode, ownership hoặc mount |
| `Read-only file system` | Root filesystem hoặc mount chỉ đọc |
| `ImagePullBackOff` | Runtime registry pull, image reference, credentials hoặc platform |

Ghi lại command đầy đủ, exit code, error đầu tiên và phase gần nhất. Lỗi Docker socket không được chữa bằng cách đổi buildpack; lỗi UID của volume không được chữa bằng cách pull lại builder.

## 2. Kiểm tra Docker daemon trước khi chạy Buildpacks

Spring Boot Maven/Gradle plugin cần truy cập **Docker-compatible daemon** để chạy builder và tạo image. Spring Boot Maven plugin có thể đọc Docker CLI configuration để xác định context hiện tại; nếu không lấy được context/connection information, plugin dùng kết nối local mặc định. Plugin cũng hỗ trợ cấu hình host, context và TLS riêng.

### 2.1. Ba lệnh đầu tiên

```bash
docker version
docker info
docker context ls
```

Cách đọc:

- `docker version` hiển thị phần **Client** và **Server**. Nếu Client có nhưng Server không có hoặc command báo lỗi kết nối, tập trung vào daemon/connection.
- `docker info` kiểm tra daemon có phản hồi và cung cấp storage driver, architecture, rootless/security options.
- `docker context ls` liệt kê các daemon endpoints mà Docker CLI có thể chọn.

Nếu `docker version` không lấy được Server section, chưa cần chạy Maven/Gradle Buildpacks. Hãy khắc phục đường kết nối Docker trước.

### 2.2. Context và environment variables

Docker CLI có thể dùng context khác với daemon local. Kiểm tra:

```bash
docker context show
docker context inspect "$(docker context show)"
env | grep -E '^(DOCKER_HOST|DOCKER_CONTEXT|DOCKER_CONFIG|DOCKER_TLS_VERIFY|DOCKER_CERT_PATH)='
```

| Biến | Tác động |
| --- | --- |
| `DOCKER_CONFIG` | Thư mục Docker CLI config/context; mặc định thường là `$HOME/.docker` |
| `DOCKER_CONTEXT` | Chọn context; trong Spring Boot Maven plugin, biến này override `DOCKER_HOST` khi tìm context |
| `DOCKER_HOST` | Endpoint Docker daemon, ví dụ Unix socket hoặc TCP host |
| `DOCKER_TLS_VERIFY` | Bật xác minh TLS khi dùng kết nối HTTPS/TLS |
| `DOCKER_CERT_PATH` | Thư mục certificate/key client khi TLS được bật |

Lỗi thường gặp là developer chuyển sang remote Docker context để build trên máy khác, sau đó CI/terminal vẫn giữ `DOCKER_CONTEXT` hoặc `DOCKER_HOST` cũ. Docker CLI và Spring Boot plugin có thể vì vậy kết nối tới daemon khác nhau.

Nếu muốn dùng local context mặc định, bỏ các override không chủ đích trong đúng shell/job rồi kiểm tra lại `docker context show` và `docker info`. Không xóa global configuration khi chưa biết các project khác có dùng hay không.

### 2.3. Kiểm tra endpoint Docker daemon

Trên Linux, endpoint local thường là Unix socket `/var/run/docker.sock`. Docker rootless thường dùng socket trong user runtime directory, ví dụ `unix:///run/user/<uid>/docker.sock`. Docker Desktop trên Windows thường dùng named pipe/context do Desktop quản lý; WSL2 có thể cần Docker Desktop WSL integration.

Nếu dùng TCP daemon, xác nhận hostname/IP và port đúng, daemon đang listen, firewall/network route cho phép runner truy cập, TLS client certificate/CA đúng và identity có quyền. Không mở Docker API công khai không xác thực để “thử nhanh”: Docker API có quyền rất mạnh trên host chạy daemon.

### 2.4. Lỗi Docker socket permission

Thông báo ví dụ:

```text
permission denied while trying to connect to the Docker daemon socket
unix:///var/run/docker.sock
```

Đây là lỗi quyền truy cập socket ở **host/runner**, xảy ra trước khi CNB builder chạy. Trên Linux:

```bash
id
ls -l /var/run/docker.sock
stat -c '%U %G %a %n' /var/run/docker.sock
```

So sánh user/group của process với owner/group socket. Docker thường cấp quyền socket cho root và một group được cấu hình. Thêm user vào group `docker` có thể cấp quyền tương đương root trên host; chỉ thực hiện theo chính sách quản trị runner và hiểu rõ tác động bảo mật. Sau khi thay group membership, cần session mới để quyền có hiệu lực.

Với rootless Docker:

```bash
systemctl --user status docker
printf '%s\n' "$DOCKER_HOST"
docker context show
```

Đừng mặc định socket rootless nằm ở `/var/run/docker.sock`.

**Không chữa lỗi socket bằng cách chạy toàn bộ CI dưới root hoặc bật container privileged.** Xác định đúng daemon/socket và cấp quyền tối thiểu cho runner identity.

### 2.5. Docker Desktop và Windows/WSL

Trên Windows PowerShell:

```powershell
docker version
docker info
docker context ls
$env:DOCKER_HOST
$env:DOCKER_CONTEXT
$env:DOCKER_CONFIG
```

Nếu CLI không kết nối được daemon:

1. Kiểm tra Docker Desktop đã khởi động hoàn tất chưa.
2. Kiểm tra context và engine Linux/Windows phù hợp với image.
3. Nếu chạy trong WSL2, kiểm tra WSL integration cho đúng distribution.
4. Kiểm tra environment variables còn sót từ terminal/session cũ.
5. Xem Docker Desktop diagnostics/service logs nếu CLI không lấy được Server information.

Spring Boot CNB image thường là Linux container. Docker Desktop cần engine/VM Linux phù hợp để chạy builder/run images Linux; Windows container mode có thể khiến Linux builder không chạy được.

## 3. Phân biệt daemon error với registry/network error

Khi Docker daemon hoạt động, xác định nó có pull được builder và run image hay không.

```bash
docker pull paketobuildpacks/builder-jammy-base:latest
```

Chỉ dùng lệnh này nếu project thực sự dùng builder đó. Lấy **builder name thực tế** từ Maven/Gradle configuration hoặc build log; không pull image tùy ý rồi suy ra project đã cấu hình đúng.

| Error | Khả năng | Kiểm tra |
| --- | --- | --- |
| `unauthorized` / `401` | Registry credentials thiếu/sai | Username/token và quyền pull |
| `denied` / `403` | Identity không có quyền đọc repository | Repository ACL, namespace |
| `manifest unknown` | Sai image name/tag/digest | Builder/run image reference |
| `x509: certificate signed by unknown authority` | Docker host không trust CA | CA/TLS của daemon/registry |
| `no such host` | DNS không phân giải | DNS resolver/network |
| `i/o timeout` | Firewall/proxy/route hoặc registry chậm | Network từ Docker host |
| `no space left on device` | Storage của daemon hết dung lượng | Disk/inodes/cache |

**Docker daemon kéo builder/run image**; sau khi builder container chạy, chính builder có thể cần tải buildpack dependencies, JDK, Maven/Gradle artifacts hoặc metadata. Network của builder container có thể khác đường network của Docker daemon. Vì vậy `docker pull` thành công chưa chứng minh mọi download trong buildpack đều thành công.

### 3.1. Proxy và CA trong builder container

Nếu log cho thấy builder không tải được artifact từ Maven repository hoặc vendor endpoint, xác định hostname của request bị lỗi. Có thể cần cấu hình `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` cho môi trường buildpack theo hướng dẫn của builder. Spring Boot plugin cho phép truyền environment variables vào builder; Paketo Java buildpacks có thể dùng proxy variables.

Ví dụ fragment Maven:

```xml
<image>
    <env>
        <HTTP_PROXY>http://proxy.corp.example:8080</HTTP_PROXY>
        <HTTPS_PROXY>http://proxy.corp.example:8080</HTTPS_PROXY>
        <NO_PROXY>localhost,127.0.0.1,.corp.example</NO_PROXY>
    </env>
</image>
```

Đây là fragment minh họa, không phải POM hoàn chỉnh. Thay proxy/host bằng cấu hình thực tế. Không ghi username/password proxy trực tiếp vào POM hoặc log. Nếu private CA cần trust trong builder, cài certificate theo cơ chế binding/CA trust mà builder hỗ trợ; trust của Docker daemon không tự động bảo đảm mọi process trong builder có cùng trust store.

### 3.2. Download nào được thực hiện ở đâu?

| Download | Thành phần thực hiện | Kiểm tra |
| --- | --- | --- |
| Builder image | Docker daemon | Docker pull, daemon logs, registry auth |
| Run image | Docker daemon/lifecycle tùy flow | Image reference, registry auth, daemon network |
| Buildpack/JDK/dependency | Process bên trong builder | Builder logs, proxy, DNS, CA, repository config |
| Application image push | Docker daemon/plugin publish flow | Target registry, publish credentials, write permission |

Khi thấy timeout, đừng đổi credentials trước khi biết request đi tới host nào.

## 4. Chẩn đoán Spring Boot plugin và CNB builder

### 4.1. Maven và Gradle command

Maven:

```bash
./mvnw -B -ntp -e spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/team/diagnostic-app:1.0.0
```

Goal `spring-boot:build-image` phù hợp để gọi trực tiếp từ CLI; nó fork lifecycle để bảo đảm package phase đã chạy. Nếu goal được bind vào lifecycle, dùng `build-image-no-fork` theo cấu hình tương ứng.

Gradle:

```bash
./gradlew bootBuildImage --stacktrace --info \
  --imageName=registry.example.com/team/diagnostic-app:1.0.0
```

Các lệnh trên minh họa tạo local image. Việc push cần publish option/configuration riêng. Khi chẩn đoán, không bật verbose/debug logs trên runner chứa secrets nếu chưa có cơ chế redact; Maven `-X` và Gradle `--debug` có thể in thông tin cấu hình nhạy cảm.

### 4.2. Builder và run image

CNB builder image chứa buildpacks và lifecycle dùng để detect/build ứng dụng. Run image cung cấp nền runtime cho application image. Spring Boot plugin chọn builder mặc định nếu không cấu hình; builder metadata thường chỉ định run image tương thích.

Có thể override builder/run image:

```xml
<image>
    <builder>paketobuildpacks/builder-jammy-base:latest</builder>
    <runImage>paketobuildpacks/run-jammy-base:latest</runImage>
</image>
```

Đây là fragment. Trong production nên pin builder/run image theo version hoặc digest đã phê duyệt thay vì dùng tag mutable `latest`. Không chọn builder và run image bất kỳ chỉ vì cả hai đều pull được.

**Builder và run image phải tương thích về stack/lifecycle/mixins.** Nếu thay run image bằng image khác stack hoặc thiếu thành phần mà launch layer cần, image có thể build thất bại hoặc build xong nhưng không launch được.

### 4.3. Pull policy và cache

Spring Boot Maven plugin hỗ trợ pull policy cho builder/run images: `ALWAYS`, `NEVER` và `IF_NOT_PRESENT`.

| Policy | Hành vi | Khi dùng |
| --- | --- | --- |
| `ALWAYS` | Luôn thử pull image từ registry | Cần kiểm tra kết nối hoặc nhận version theo reference |
| `IF_NOT_PRESENT` | Dùng local image nếu có, nếu chưa thì pull | Phát triển thông thường với tag/version đã quản lý |
| `NEVER` | Không pull; yêu cầu image đã có local | Offline build có chuẩn bị image/cache trước |

Nếu dùng `NEVER` nhưng builder chưa có local, build fail dù registry có image. Nếu dùng tag mutable cùng `IF_NOT_PRESENT`, local cache có thể giữ builder cũ. Khi nghi mismatch, kiểm tra local image ID/digest và pull policy thay vì xóa toàn bộ cache ngay.

### 4.4. Đọc CNB lifecycle logs

CNB lifecycle có năm build phases theo thứ tự:

1. **Analyze:** đọc metadata/layer của image trước đó và xác minh khả năng truy cập registry để chuẩn bị cho lần build mới.
2. **Detect:** buildpacks kiểm tra ứng dụng có phù hợp và tạo build plan không.
3. **Restore:** khôi phục layer cache phù hợp dựa trên metadata từ Analyze và build plan từ Detect.
4. **Build:** buildpacks xử lý source/artifact và tạo build/launch layers.
5. **Export:** ghép các layer và xuất OCI image.

**Launch là bước runtime sau khi Export:** launcher là entrypoint của OCI image và khởi chạy process được chọn khi container chạy; đây không phải build phase thứ sáu.

Lỗi theo từng giai đoạn gợi ý nguyên nhân:

- Analyze fail: không đọc được metadata image trước đó, registry không cho phép truy cập hoặc reference image cũ không hợp lệ.
- Detect fail: không nhận diện đúng application artifact, builder không có buildpack phù hợp hoặc buildpack version không tương thích.
- Restore fail: cache/layer metadata/volume lỗi hoặc không đọc được.
- Build fail: thiếu JDK/dependency, lỗi buildpack, proxy/DNS/CA hoặc source configuration.
- Export fail: Docker storage, layer write, quyền hoặc dung lượng.
- Launch/runtime fail: launcher, process type/start command, run image hoặc cấu hình runtime không tương thích.

### 4.5. Inspect builder và image

Nếu có Pack CLI:

```bash
pack inspect-builder paketobuildpacks/builder-jammy-base:latest
pack inspect-image registry.example.com/team/diagnostic-app:1.0.0
```

Thay builder/image bằng reference thực tế. `pack inspect-image` giúp xem run image, buildpacks, process types và metadata của image do Buildpacks tạo. Nếu Pack CLI không có, dùng Docker image inspection và log từ Spring Boot plugin; không cần cài thêm công cụ chỉ để chạy một lệnh nếu môi trường đã có đủ evidence.

### 4.6. Lỗi detection thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `no buildpack groups passed detection` | Builder không tìm được buildpack group phù hợp | Xác nhận JAR/WAR đã tạo, builder có Java buildpack |
| Không thấy executable archive | Build goal/source artifact sai | Chạy package/verify, kiểm tra target JAR |
| Unsupported Java version | Java version ngoài khả năng buildpack | Chọn builder/buildpack hỗ trợ hoặc version tương thích |
| Download dependency fail | Builder network/proxy/repository | Kiểm tra hostname, proxy, CA và Maven repository |
| Run image/stack mismatch | Builder và run image không tương thích | Dùng run image từ builder metadata hoặc cặp được phê duyệt |
| Export/cache write fail | Docker storage/volume/permission | Kiểm tra daemon disk, cache volume và logs |

Với Maven, `spring-boot:build-image` bảo đảm package phase chạy trước khi tạo image. Với Gradle, task `bootBuildImage` phụ thuộc executable archive task tương ứng. Nếu source archive không đúng, kiểm tra build output trước khi thay builder.

## 5. Chẩn đoán kiến trúc CPU và image platform

Một image có thể build thành công trên máy developer nhưng không chạy trên production node vì **OS/CPU architecture không tương thích**.

| Platform | Nền tảng |
| --- | --- |
| `linux/amd64` | Linux x86-64, thường gặp ở Intel/AMD servers |
| `linux/arm64` | Linux ARM 64-bit, ví dụ ARM servers/Apple Silicon VM |
| `windows/amd64` | Windows container trên x86-64 |
| `linux/arm/v7` | Linux ARM 32-bit variant |

Spring Boot JAR chứa Java bytecode thường portable giữa kiến trúc, nhưng **JRE, native libraries, OS packages và run image** có platform riêng. Java bytecode không biến một Linux AMD64 run image thành ARM64 image.

### 5.1. Kiểm tra máy và image

Trên Linux/macOS:

```bash
uname -m
docker info --format '{{.OSType}}/{{.Architecture}}'
docker image inspect --format '{{.Os}}/{{.Architecture}}' \
  registry.example.com/team/diagnostic-app:1.0.0
```

Các output phổ biến của `uname -m` là `x86_64` hoặc `aarch64`. Docker image inspect hiển thị platform của image local đã build/pull.

Trên Windows PowerShell:

```powershell
$env:PROCESSOR_ARCHITECTURE
docker info --format '{{.OSType}}/{{.Architecture}}'
docker image inspect --format '{{.Os}}/{{.Architecture}}' registry.example.com/team/diagnostic-app:1.0.0
```

So sánh OS/architecture của image với Docker daemon và node triển khai. Mac Apple Silicon có thể chạy image AMD64 qua emulation; build pass trên máy developer không chứng minh image có native ARM64 support.

### 5.2. Kiểm tra remote multi-platform manifest

Nếu image được publish và có thể có nhiều platform manifests:

```bash
docker buildx imagetools inspect registry.example.com/team/diagnostic-app:1.0.0
```

Lệnh này hiển thị manifest/index và platform registry công bố; cần Docker Buildx và quyền đọc registry. Nếu chỉ có `linux/amd64` mà production node là ARM64, runtime có thể báo `no matching manifest for linux/arm64`.

`docker image inspect` trên máy local thường cho platform của image đã pull vào daemon đó. Để xem các platform trong remote manifest list, dùng công cụ đọc registry index như `buildx imagetools inspect`.

### 5.3. Phân biệt lỗi kiến trúc

| Lỗi | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| `no matching manifest for linux/arm64` | Registry không có platform node cần | Publish multi-platform image hoặc build riêng platform |
| `exec format error` | Binary/entrypoint không phù hợp kiến trúc/định dạng | Kiểm tra image architecture, binary và shebang |
| Native library load fail | Native dependency sai kiến trúc/ABI | Rebuild native layer cho target platform |
| Image chạy chậm trên laptop ARM | Đang chạy image AMD64 qua emulation | Dùng image ARM64 native nếu builder/run image hỗ trợ |

Không giả định Maven/Gradle `bootBuildImage` có cùng một tùy chọn `--platform` như `docker run`/Buildx. `docker run --platform linux/amd64` chỉ yêu cầu runtime chọn platform phù hợp và có thể cần emulation; nó **không** biến image đã build thành ARM64 và không thay thế quy trình build/publish multi-architecture được CNB hỗ trợ.

### 5.4. Thiết kế release cho nhiều kiến trúc

- Chọn builder và run image có hỗ trợ từng target platform.
- Build/test trên native runner cho từng kiến trúc khi có thể.
- Nếu dùng emulation, kiểm chứng tính tương thích; đừng coi emulation là thay thế đầy đủ native test.
- Tạo manifest/index đa nền tảng bằng quy trình được CNB/registry hỗ trợ và kiểm thử.
- Inspect remote manifest trước deploy.
- Test ít nhất một node/runner thật cho từng kiến trúc được công bố.

## 6. Quyền user và file ownership trong CNB images

Spring Boot documentation nêu rằng image tạo bằng Buildpacks **build và run với non-root users vì lý do bảo mật**. Đây là hành vi có chủ ý. Ứng dụng ghi file vào đường dẫn chỉ root mới ghi được có thể build thành công nhưng fail khi container chạy.

Trước tiên xác định **process user thực tế** trong image:

```bash
docker image inspect --format '{{.Config.User}}' \
  registry.example.com/team/diagnostic-app:1.0.0
```

Giá trị có thể là UID, dạng `UID:GID` hoặc tên user tùy image. Không mặc định mọi CNB image đều dùng UID `1000` hay `10001`; hãy đọc metadata image thực tế. Với image tối giản không có shell/coreutils, đừng giả định `sh`, `id` hay `ls` đều tồn tại.

### 6.1. Quyền POSIX cơ bản

| Bit | File | Directory |
| --- | --- | --- |
| `r` | Đọc nội dung | Liệt kê tên file |
| `w` | Sửa nội dung | Tạo/xóa/đổi tên entry (còn phụ thuộc quyền directory và filesystem) |
| `x` | Thực thi file | Đi qua/traverse directory |

Ví dụ:

- `0644`: owner đọc/ghi; group và others đọc.
- `0640`: owner đọc/ghi; group đọc; others không có quyền.
- `0755`: owner đọc/ghi/thực thi; group/others đọc/thực thi.
- `0700`: chỉ owner có quyền đọc/ghi/traverse.

Một file có mode `0644` vẫn không đọc được nếu một thư mục cha không cho process traverse. Directory có `r` nhưng thiếu `x` cũng không đủ để truy cập file bên trong.

### 6.2. Kiểm tra UID/GID và mode trên host

Trên Linux:

```bash
id
stat -c '%u:%g %a %n' ./data
stat -c '%u:%g %a %n' ./data/*
namei -l ./data
```

- `id` cho biết UID/GID của process hiện tại.
- `stat` hiển thị numeric owner, group và permission mode.
- `namei -l` hiển thị quyền trên từng thành phần của đường dẫn.

Trên macOS, cú pháp stat khác; dùng `stat -f '%u:%g %Lp %N' path`. Trên Windows, quyền host chịu ảnh hưởng của NTFS ACL và Docker Desktop file-sharing translation; kiểm tra bằng `Get-Acl` hoặc `icacls`.

Đừng chỉ nhìn username. Kernel quyết định truy cập bằng numeric UID/GID và ACL; hai container cùng tên user nhưng UID khác vẫn có thể không truy cập được cùng volume.

### 6.3. Bind mount giữ quan hệ ownership từ host

Ví dụ:

```bash
mkdir -p ./data
docker run --rm \
  -p 127.0.0.1:18080:8080 \
  --mount type=bind,source="$PWD/data",target=/data \
  registry.example.com/team/diagnostic-app:1.0.0
```

Container thấy host directory qua `/data`. Nếu host directory thuộc `root:root` với mode `0755`, process CNB non-root thường không thể tạo file ở đó. Lỗi có thể xuất hiện như `java.nio.file.AccessDeniedException` hoặc `Permission denied`.

Cách xử lý:

1. Xác định UID/GID image thực tế và owner host directory.
2. Chọn ownership/group phù hợp cho dữ liệu ứng dụng.
3. Cấp đúng quyền đọc/ghi/traverse cho process hoặc group được phép.
4. Kiểm tra lại bằng một lần chạy container.
5. Ghi nhận permission policy cho môi trường deploy để tránh lỗi lặp lại.

Không dùng `chmod -R 777` làm cách chữa chung. Nó mở quyền ghi cho mọi user và có thể tạo rủi ro sửa/xóa dữ liệu.

### 6.4. Named volume và bind mount khác nhau

| Kiểu mount | Ownership ban đầu | Điểm cần kiểm tra |
| --- | --- | --- |
| Bind mount | Lấy từ directory/file trên host | Host UID/GID, ACL, mode, SELinux label nếu có |
| Docker named volume | Do Docker quản lý; nội dung có thể được khởi tạo từ image khi mount lần đầu | Owner/mode của volume data, volume cũ |
| Kubernetes PVC | Storage driver/CSI và security context phối hợp | `fsGroup`, volume driver, access mode |
| `tmpfs`/`emptyDir` | Theo runtime/orchestrator và mount options | Writable path, quota, lifecycle |

Named volume không tự động bảo đảm process non-root có quyền ghi mọi dữ liệu. Volume đã tồn tại từ lần chạy trước có thể giữ owner/mode cũ. Kiểm tra volume và quá trình khởi tạo dữ liệu trước khi đổi permission.

### 6.5. Rootless Docker và UID mapping

Rootless Docker chạy daemon/container trong user namespace và ánh xạ UID/GID container sang host IDs. UID hiển thị trong container không nhất thiết bằng UID trên host filesystem.

Nếu bind mount lỗi permission trên rootless engine:

- Xác nhận đúng rootless daemon/context.
- Xem UID/GID mapping theo tài liệu Docker.
- Kiểm tra host path ownership dưới user chạy daemon.
- Đừng giả định `chown 1000:1000` trên host luôn tương ứng UID `1000` trong container.
- Thử trên directory dữ liệu riêng có thể khôi phục trước khi đổi quyền production.

## 7. Phân biệt Permission denied, Read-only và No space

Ba lỗi này cần cách xử lý khác nhau:

| Error | Ý nghĩa | Hướng kiểm tra |
| --- | --- | --- |
| `Permission denied` / `EACCES` | Process không có quyền truy cập | UID/GID, mode, ACL, parent directories |
| `Read-only file system` / `EROFS` | Filesystem/mount được gắn read-only | `readOnlyRootFilesystem`, bind mount flags, volume |
| `No space left on device` / `ENOSPC` | Hết blocks, inodes hoặc quota | Disk, inode, Docker storage, volume quota |

### 7.1. Container chạy với read-only root filesystem

Container có thể được cấu hình `readOnlyRootFilesystem: true`. Ứng dụng không thể ghi vào root filesystem, kể cả khi directory thuộc đúng user. Đây là lỗi `EROFS`, không phải `EACCES`.

Thiết kế rõ các đường dẫn cần ghi:

- Dữ liệu bền vững: volume mount riêng, ví dụ `/data`.
- File tạm: `emptyDir`/tmpfs hoặc mount `/tmp` phù hợp.
- Logs: ưu tiên stdout/stderr để runtime thu thập.
- Cache: xác định có thực sự cần persist không và đặt quota/lifecycle.

Không tắt read-only root filesystem chỉ để che lỗi nếu ứng dụng có thể dùng volume/temp path riêng.

### 7.2. Kiểm tra dung lượng Docker

Các lệnh đọc trạng thái:

```bash
docker system df
docker system df -v
df -h
df -i
```

`docker system df` hiển thị dung lượng images, containers, local volumes và build cache. `df -h` xem blocks; `df -i` xem inode trên Linux. Một filesystem có thể còn GB nhưng hết inodes.

Không chạy `docker system prune -a --volumes` theo phản xạ. Lệnh prune có thể xóa image/cache/volume cần thiết; hãy kiểm tra tài nguyên, owner/lifecycle và backup trước cleanup. Buildpacks sử dụng cache volumes để tăng tốc; xóa chúng có thể làm build sau tải lại nhiều layers.

### 7.3. OOM và resource limits

Nếu builder/container bị dừng đột ngột hoặc exit code thể hiện OOM:

- Kiểm tra memory limit của Docker Desktop/VM/runner.
- Kiểm tra daemon logs và kernel OOM events trên Linux.
- Kiểm tra container memory usage/limits.
- Phân biệt OOM của CNB builder với OOM của Spring Boot runtime.
- Điều chỉnh resource phù hợp workload; không tăng vô hạn hoặc bỏ mọi giới hạn.

Memory dùng trong builder/lifecycle khác với heap của ứng dụng runtime.

## 8. Chẩn đoán file permission khi ứng dụng Java ghi dữ liệu

Giả sử app muốn ghi file vào directory cấu hình bởi `APP_DATA_DIR`. Code nên nhận path rõ ràng và xử lý lỗi để log được nguyên nhân:

```java
package dev.example.diagnostic;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DataFileProbe {

    private DataFileProbe() {
    }

    public static Path writeProbe() throws IOException {
        String configured = System.getenv()
                .getOrDefault("APP_DATA_DIR", "/data");

        Path directory = Path.of(configured).toAbsolutePath().normalize();
        Files.createDirectories(directory);

        Path file = directory.resolve("permission-probe.txt");
        Files.writeString(
                file,
                "write-ok" + System.lineSeparator(),
                StandardCharsets.UTF_8
        );

        return file;
    }
}
```

Đây là class Java 17 độc lập, không phải Spring Boot application hoàn chỉnh. Có thể gọi `DataFileProbe.writeProbe()` trong startup check hoặc integration test có kiểm soát. Nếu không muốn ứng dụng tự tạo directory, hãy yêu cầu mount path tồn tại và fail với log rõ ràng.

Kiểm tra:

- `APP_DATA_DIR` có đúng path trong container không?
- Directory có được mount không?
- Process UID/GID có quyền traverse và write không?
- Mount có `ro` hoặc filesystem read-only không?
- Directory có đủ dung lượng/inodes không?
- Có SELinux/AppArmor/storage policy chặn không?
- Nếu dùng Kubernetes, volume driver có hỗ trợ ownership change theo `fsGroup` không?

Không log secret hoặc nội dung file dữ liệu thực trong quá trình diagnostic.

## 9. Kubernetes: runAsNonRoot, fsGroup và volume permissions

Khi image chạy trong Kubernetes, runtime security context có thể thay đổi user/group và filesystem permissions so với local Docker.

Ví dụ Pod fragment:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: diagnostic-app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 2000
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: app
      image: registry.example.com/team/diagnostic-app:1.0.0
      ports:
        - containerPort: 8080
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: app-data
          mountPath: /data
        - name: app-tmp
          mountPath: /tmp
  volumes:
    - name: app-data
      emptyDir: {}
    - name: app-tmp
      emptyDir: {}
```

Đây là ví dụ security context cần đối chiếu với image thật và storage driver. `runAsUser: 1000` chỉ là giá trị minh họa; lấy UID/GID thực tế từ image metadata và kiểm tra cluster policy. `fsGroup: 2000` cung cấp group identity cho volume hỗ trợ fsGroup; nó không tự thay UID process.

`fsGroupChangePolicy: OnRootMismatch` có thể giảm thời gian đổi ownership cho volume lớn bằng cách chỉ đổi khi owner/mode của root volume không khớp. Trường này chỉ có tác dụng với volume types hỗ trợ fsGroup; CSI driver có thể tự xử lý mount group. Secret, ConfigMap và `emptyDir` có hành vi/giới hạn riêng.

### 9.1. Khi Pod báo permission denied

Lấy trạng thái và events:

```bash
kubectl describe pod diagnostic-app
kubectl get pod diagnostic-app -o wide
kubectl logs diagnostic-app --all-containers=true --tail=200
```

Nếu container restart:

```bash
kubectl logs diagnostic-app --previous --tail=200
```

Kiểm tra:

1. Image reference và node architecture.
2. Pod/container `securityContext`: `runAsNonRoot`, `runAsUser`, `runAsGroup`, `fsGroup`.
3. Volume mount đúng path và có read-only không.
4. PVC/CSI driver hỗ trợ ownership/group handling không.
5. File/directory mode của dữ liệu tồn tại từ lần deploy trước.
6. App đang ghi vào `/data`, `/tmp` hay root filesystem.
7. Pod events có báo mount failure, image pull failure hoặc security admission rejection không.

`kubectl exec` chỉ hữu ích nếu image có shell/diagnostic binary. Image tối giản có thể không có `/bin/sh`; khi đó dùng logs, metadata, ephemeral debug container theo policy hoặc diagnostic image phù hợp.

### 9.2. Phân biệt ImagePullBackOff với app permission failure

- `ImagePullBackOff`: container runtime chưa kéo được image. Kiểm tra registry auth, image path/tag/digest, TLS và platform manifest.
- Pod đã start rồi crash với `Permission denied`: image đã được pull; kiểm tra user, filesystem, volume và app logs.
- `CreateContainerError` có thể đến từ runtime configuration, mount hoặc entrypoint; đọc events để phân loại.

Đừng sửa `fsGroup` khi Pod còn chưa pull được image. Đừng đổi registry token khi app đã chạy và chỉ fail lúc ghi file.

## 10. Thu thập logs và state để khoanh vùng

### 10.1. Docker container logs

Khi container còn tồn tại:

```bash
docker ps -a
docker logs --tail=200 diagnostic-app
docker inspect --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Error}}' diagnostic-app
docker inspect --format '{{.Config.User}}' diagnostic-app
# OS/architecture của image, không phải metadata của container
docker image inspect --format '{{.Os}}/{{.Architecture}}' registry.example.com/team/diagnostic-app:1.0.0
```

Nếu cần giữ container để điều tra, tạo container với tên riêng và không dùng `--rm` trong lần chạy diagnostic:

```bash
docker run -d --name diagnostic-app \
  -p 127.0.0.1:18080:8080 \
  registry.example.com/team/diagnostic-app:1.0.0

docker logs --tail=200 diagnostic-app
docker inspect --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Error}}' diagnostic-app
```

Sau khi hoàn tất, chỉ xóa container thử nghiệm do chính bạn tạo:

```bash
docker rm -f diagnostic-app
```

Không dùng tên container của ứng dụng khác. `docker rm -f` xóa container được chỉ định.

### 10.2. Docker daemon logs

Trên Linux systemd:

```bash
sudo journalctl -u docker --since "15 minutes ago"
```

Quyền đọc daemon logs có thể cần quyền quản trị. Trên Docker Desktop, dùng Diagnostics/Troubleshoot và log collection của Desktop. Trên Windows Server, kiểm tra service/Event Viewer theo cách vận hành của máy.

Nếu daemon treo hoặc restart, daemon logs thường cung cấp thông tin rõ hơn application logs vì app có thể chưa được khởi chạy.

### 10.3. Maven/Gradle diagnostic output

Maven:

```bash
./mvnw -B -ntp -e spring-boot:build-image
```

Gradle:

```bash
./gradlew bootBuildImage --stacktrace --info
```

`-e`/`--stacktrace` giúp thấy exception chain; `--info` cung cấp thêm task output. Chỉ bật debug đầy đủ khi cần và trên runner phù hợp, vì log chi tiết có thể chứa repository URL, environment/configuration và thông tin nhạy cảm.

## 11. Bảng lỗi thường gặp và cách sửa theo bằng chứng

| Hiện tượng | Nguyên nhân có khả năng cao | Bước xử lý |
| --- | --- | --- |
| `Cannot connect to Docker daemon` | Engine chưa chạy hoặc sai endpoint/context | `docker info`, context, `DOCKER_HOST`, service |
| `permission denied` với docker.sock | Runner user không được truy cập socket | `id`, socket owner/group, rootless context |
| Docker CLI hoạt động nhưng Maven plugin fail | Plugin đọc context/config khác do env | So sánh `DOCKER_CONFIG`, `DOCKER_CONTEXT`, `DOCKER_HOST` trong cùng process |
| Client/API version error | Docker client/plugin và Engine API không tương thích | Kiểm tra client/server versions, cập nhật theo matrix hỗ trợ |
| Builder pull 401 | Thiếu quyền đọc builder registry | Cấu hình builder registry credentials đúng host |
| Builder pull x509 | Daemon không trust registry CA | Cài CA theo Docker Engine/registry policy |
| Buildpack download timeout | Builder network/proxy/DNS | Kiểm tra hostname lỗi, proxy và CA |
| `no buildpack groups passed detection` | Source artifact/builder không phù hợp | Kiểm tra executable JAR, builder/buildpack versions |
| Build phase fail khi tải JDK | Buildpack network hoặc Java version constraint | Kiểm tra buildpack logs, proxy, supported version |
| Export phase `no space left on device` | Docker data/cache volume đầy | `docker system df -v`, host disk/inodes |
| Build dùng builder cũ | Pull policy/cache giữ image cũ | Kiểm tra builder digest và pull policy |
| Run image không tương thích | Builder/run stack mismatch | Dùng run image trong builder metadata |
| `no matching manifest` | Registry không có platform node cần | Kiểm tra manifest list, publish đúng architecture |
| `exec format error` | Binary/script sai arch hoặc định dạng | Inspect OS/arch, binary và shebang |
| `AccessDeniedException` | App UID/GID không ghi được path | Inspect image user, host mount owner/mode |
| Permission denied đọc secret/config | File mode/ACL không cho process đọc | Kiểm tra UID/GID, file mode và mount |
| `Read-only file system` | Ghi vào root filesystem hoặc read-only mount | Chuyển sang writable volume/tmpfs |
| `No space left on device` khi ghi app data | Volume/disk/inode/quota hết | Kiểm tra storage và quota |
| Pod `ImagePullBackOff` | Runtime pull credentials/path/platform | Pod events, imagePullSecret, registry manifest |
| Pod crash sau khi start | App/config/permission/runtime lỗi | Previous logs, state, volume và securityContext |

## 12. Quy trình chẩn đoán theo thứ tự

**Bước 1 — Ghi lại command và phase lỗi.** Lưu Maven/Gradle command, error đầu tiên, exit code và thời điểm. Xác định lỗi xảy ra trước daemon connection, lúc pull builder, detect/build/export hay khi chạy container.

**Bước 2 — Xác minh Docker Engine.** Chạy `docker version`, `docker info`, `docker context show`. Nếu Server section không hoạt động, xử lý daemon/context/socket/TLS trước.

**Bước 3 — Kiểm tra builder/run images.** Xác nhận đúng builder/run image và pull policy. Thử pull chính reference đó; kiểm tra auth, CA, DNS, disk.

**Bước 4 — Đọc CNB logs.** Xác định build phase analyze/detect/restore/build/export; phân biệt lỗi launcher/runtime xảy ra sau khi image đã export. Kiểm tra source artifact, buildpack support, dependency download, cache và run image compatibility.

**Bước 5 — Xác định platform.** So sánh OS/architecture của daemon, local image, remote manifest và production node. Kiểm tra native libraries nếu Java app dùng JNI hoặc dependencies native.

**Bước 6 — Kiểm tra process user và file path.** Đọc `Config.User`; kiểm tra UID/GID, mode, ACL, parent directories, bind/named volumes và read-only mounts.

**Bước 7 — Kiểm tra runtime độc lập.** Chạy/pull đúng image, lấy logs/state/exit code. Nếu Kubernetes, đọc Pod events và previous logs để phân biệt pull error với app crash.

**Bước 8 — Sửa đúng một nguyên nhân và chạy lại.** Ghi rõ thay đổi, command kiểm chứng và kết quả. Không cleanup toàn bộ Docker data root hoặc cấp root/privileged khi chưa có bằng chứng.

## 13. Các biện pháp khắc phục an toàn

| Tình huống | Cách khắc phục phù hợp | Tránh |
| --- | --- | --- |
| Daemon không chạy | Khởi động Docker service/Desktop theo môi trường | Chạy thêm nhiều daemon không rõ context |
| Sai Docker context | Chọn context đúng cho process/job | Sửa global config của mọi project |
| Socket permission | Cấp quyền cho runner identity theo policy | Chạy cả build dưới root hoặc mở socket rộng |
| Registry CA | Cài CA chain tin cậy đúng daemon/runtime | Tắt TLS/insecure registry trên production |
| Builder mismatch | Pin builder/run image tương thích | Chọn tùy ý tag `latest` |
| Builder download fail | Cấu hình proxy/CA/repository đúng host | Đưa credentials vào build log |
| Disk full | Dọn tài nguyên đã xác định owner/lifecycle, tăng capacity | `docker system prune -a --volumes` không kiểm tra |
| Wrong architecture | Build/publish platform phù hợp, kiểm tra manifest | Cho rằng `docker run --platform` đã rebuild image |
| Volume permission | Điều chỉnh owner/group/mode đúng process | `chmod 777` |
| Root filesystem read-only | Mount writable data/temp path theo policy | Bật writable root filesystem vô điều kiện |
| Kubernetes fsGroup | Dùng group phù hợp và volume driver hỗ trợ | Đặt UID/GID ngẫu nhiên không kiểm tra image |
| Debug logs | Dùng `-e`, `--stacktrace`, `--info` rồi thu evidence | Bật debug dài hạn trên runner có secrets |

## 14. Bài tập tự kiểm tra

**Tình huống A.** `docker version` hiển thị Client nhưng không có Server section; Maven `build-image` báo không kết nối được. Bắt đầu ở đâu?

*Đáp án:* Docker daemon/context/endpoint. Kiểm tra `docker info`, `docker context show`, `DOCKER_HOST`/`DOCKER_CONTEXT` và trạng thái Docker service. Chưa cần sửa buildpack.

**Tình huống B.** Docker pull builder thành công nhưng CNB báo timeout khi tải JDK. Có phải registry password sai?

*Đáp án:* Chưa chắc. Builder container có thể cần proxy/DNS/CA để tải JDK từ host khác. Xem hostname trong lifecycle logs và network của builder.

**Tình huống C.** App image chạy trên x86-64 nhưng production ARM64 báo `no matching manifest`. Vì sao?

*Đáp án:* Registry manifest không có platform `linux/arm64` phù hợp. Cần build/publish image cho platform đó hoặc multi-platform index được xác minh.

**Tình huống D.** App khởi động được nhưng ghi `/data/report.txt` báo `AccessDeniedException`. Cần kiểm tra gì?

*Đáp án:* Image `Config.User`, owner/group/mode của mount, quyền traverse directory và volume read/write. Không mặc định app chạy root.

**Tình huống E.** Container báo `Read-only file system` dù directory thuộc đúng UID. Vì sao?

*Đáp án:* Filesystem/mount được gắn read-only. Kiểm tra `readOnlyRootFilesystem`, bind mount flags và volume; chmod không biến read-only filesystem thành writable.

**Tình huống F.** Docker image inspect cho thấy `linux/amd64`, máy developer ARM64 vẫn chạy được. Có đảm bảo production ARM64 chạy native không?

*Đáp án:* Không. Developer có thể đang dùng emulation. Kiểm tra remote manifest và test trên ARM64 native runner/node.

**Tình huống G.** CNB export fail `no space left on device`, app runtime chưa chạy. Kiểm tra ở đâu?

*Đáp án:* Docker daemon storage, builder cache volumes, disk blocks/inodes và runner capacity; đây là lỗi build/export phase.

**Tình huống H.** Kubernetes Pod báo `ImagePullBackOff`; có nên thay `fsGroup`?

*Đáp án:* Không phải bước đầu. Kiểm tra Pod events, image reference, registry credentials/TLS và platform. `fsGroup` xử lý quyền volume sau khi image được pull/mount.

**Tình huống I.** Thêm user vào group `docker` sửa socket error. Có thể coi đó là quyền bình thường?

*Đáp án:* Cần đánh giá security policy vì group `docker` có thể cấp quyền tương đương root trên host. Cấp cho runner identity chuyên dụng và giới hạn job phù hợp.

**Tình huống J.** `docker image inspect` cho thấy user rỗng. Có chắc image sẽ chạy root?

*Đáp án:* Không nên kết luận chỉ từ một trường metadata chưa rõ. Kiểm tra image/buildpack process metadata và runtime behavior; Spring Boot CNB images được thiết kế build/run non-root, nhưng phải xác minh image thực tế và các override runtime.

## 15. Checklist trước khi kết luận sự cố đã được xử lý

**Docker daemon và network:**

- Docker client lấy được Server information từ đúng daemon.
- Context, host, TLS variables và Docker config path được xác định.
- Runner user có quyền truy cập socket/endpoint theo policy.
- Builder/run images pull được từ đúng registry.
- Builder network truy cập dependency/JDK sources qua proxy/CA phù hợp.
- Docker storage còn đủ disk/inodes; cache được quản lý có chủ đích.

**Buildpacks và image:**

- Source JAR/WAR đúng và được package.
- Builder có buildpack phù hợp; lifecycle logs cho biết phase lỗi.
- Builder/run images tương thích và được pin version/digest.
- Pull policy phù hợp với cache/registry.
- Image được tạo có process metadata hợp lệ và inspect được.
- Image OS/architecture phù hợp target runtime; remote manifest có platform cần thiết.

**User và filesystem:**

- `Config.User`/process UID/GID đã được kiểm tra.
- Bind mount/named volume/PVC có owner/group/mode phù hợp.
- Process có quyền traverse parent directories và đọc/ghi đúng path.
- `EACCES`, `EROFS` và `ENOSPC` được phân biệt.
- Writable data/temp paths được thiết kế rõ; root filesystem có thể giữ read-only.
- Không cần `chmod 777`, root hoặc privileged mode để ứng dụng chạy.

**Runtime và bằng chứng:**

- Container/Pod logs, exit code và events được thu thập.
- Smoke test chạy trên đúng image đã build/pull.
- Kubernetes `ImagePullBackOff` được phân biệt với application crash.
- Thay đổi được kiểm tra lại bằng command tái hiện lỗi ban đầu.
- Ghi lại nguyên nhân, thay đổi, image digest/platform và kết quả xác minh.

**Kết luận:** Chẩn đoán CNB container cần đi từ **Docker daemon/context**, qua **builder/run image và lifecycle**, tới **OS/CPU platform**, rồi **process user và filesystem mounts**. Khi phân loại đúng tầng, `docker info`, lifecycle logs, `docker image inspect`, remote manifest inspection, UID/GID và volume events sẽ chỉ ra nguyên nhân cụ thể. Hãy sửa theo evidence và kiểm tra lại đúng command/runtime đã từng lỗi.

### Tài liệu chính thức

- Spring Boot 3.3 Maven Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html
- Spring Boot 3.3 Gradle Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html
- Spring Boot 3.3 System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Docker Docs — Troubleshooting the Docker daemon: https://docs.docker.com/engine/daemon/troubleshoot/
- Docker Docs — Docker daemon configuration: https://docs.docker.com/engine/daemon/
- Docker Docs — Rootless mode and UID/GID mapping: https://docs.docker.com/engine/security/rootless/
- Cloud Native Buildpacks — Inspect your app image: https://buildpacks.io/docs/for-app-developers/how-to/build-outputs/inspect-app/
- Kubernetes — Configure a Security Context for a Pod or Container: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes — Volumes and file ownership: https://kubernetes.io/docs/concepts/storage/volumes/