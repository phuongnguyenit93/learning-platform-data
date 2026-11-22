# Chuẩn bị Docker daemon và kiểm tra kết nối từ công cụ build Spring Boot

## 1. Vấn đề cần giải quyết

Khi muốn tạo Docker/OCI image cho Spring Boot bằng **Cloud Native Buildpacks (CNB)**, bạn thường chạy một trong hai lệnh:

~~~bash
mvn spring-boot:build-image
./gradlew bootBuildImage
~~~

Hai lệnh này có thể tạo image trực tiếp từ ứng dụng Java **không cần Dockerfile**, nhưng chúng cần truy cập **Docker-compatible daemon**. Lỗi phổ biến là terminal chạy `docker --version` thành công, rồi plugin báo “Cannot connect to Docker daemon”. Nguyên nhân: **Docker CLI, Docker daemon, Docker context, image registry và Cloud Native Buildpacks là các thành phần khác nhau**.

Sau bài này, bạn sẽ biết:

1. Docker daemon là gì và vì sao Maven/Gradle build-image phải liên hệ được daemon.
2. Kiểm từng nấc `docker --version`, `docker version`, `docker info`, `docker ps`, `docker run`.
3. Chuẩn bị Docker Desktop trên Windows/macOS, Docker Engine trên Linux; nhận diện WSL2, Linux containers và Unix socket.
4. Kiểm Docker context, `DOCKER_CONTEXT`, `DOCKER_HOST`, `DOCKER_CONFIG`, TLS/certificate và user permissions.
5. Hiểu khác biệt giữa quyền của terminal, IDE, Gradle Daemon, container chạy build và CI runner.
6. Tạo một Spring Boot Java 17 app chạy được, unit test được và xây OCI image bằng Maven.
7. Tạo biến thể Gradle Kotlin DSL có task `bootBuildImage` và kiểm image ở đúng daemon.
8. Cấu hình remote Docker daemon qua context hoặc TLS, tránh kết nối TCP không bảo mật.
9. Tách lỗi Docker API khỏi lỗi pull builder/run image, registry login, CNB lifecycle, volumes và Java packaging.
10. Xây dựng quy trình preflight CI, troubleshooting và smoke test cho chính image đã tạo.

**Phiên bản ví dụ:** Spring Boot **3.5.16**, Java **17+**. Có thể dùng Maven/Gradle tương thích với Spring Boot 3.5, ưu tiên Wrapper nếu project đã tạo. Các giá trị là mốc thực hành cụ thể chứ không yêu cầu mọi project phải áp dụng đúng phiên bản lâu dài.

## 2. Sơ đồ kết nối: ai đang nói chuyện với ai?

~~~text
Developer Terminal / IDE / CI runner
           |
           |  mvn spring-boot:build-image
           |  gradle bootBuildImage
           v
  Spring Boot Maven/Gradle Plugin
           |
           |  Docker-compatible Engine API
           |  qua Unix socket, Windows npipe hoặc TCP/TLS
           v
       Docker daemon
           |
           +-- Pull builder image từ registry
           +-- Pull run image từ registry
           +-- Tạo container chạy CNB build lifecycle
           +-- Tạo/mount cache volumes và workspace
           +-- Export OCI application image vào image store
           |
           v
   docker image inspect app:tag
   docker run --rm app:tag
~~~

**Docker CLI** (`docker`) là chương trình gửi yêu cầu tới daemon qua API. **Docker daemon** (`dockerd` trên Docker Engine) là server quản lý images, containers, volumes và networking. **Docker context** là một cấu hình chọn endpoint của daemon. **Registry** là nơi lưu/distribute images qua mạng; registry **không phải daemon**.

**CNB builder image** chứa buildpacks và lifecycle. **Run image** là phần nền runtime của OCI application image. Spring Boot plugin dùng Docker API để tải/chạy những thành phần đó; nó không tương đương việc chạy `docker build` trên một Dockerfile do bạn tự viết.

### 2.1. Phân biệt từng loại kết quả kiểm tra

| Lệnh | Điều được chứng minh | Điều chưa được chứng minh |
| --- | --- | --- |
| `docker --version` | CLI binary có trong PATH | Docker daemon đang chạy hay không |
| `docker version` có cả **Client** và **Server** | CLI kết nối được một Docker daemon | Maven/Gradle process khác có cùng kết nối không |
| `docker info` | Daemon trả lời API và cung cấp cấu hình server | Pull builder/run image và CNB lifecycle sẽ thành công |
| `docker ps` | Có quyền gọi API liệt kê containers | Có đủ quyền tạo, mount và chạy builder container không |
| `docker run --rm hello-world` | Có khả năng pull (khi cần) và chạy container đơn giản | Paketo builder/JDK/image platform cụ thể có hợp lệ không |
| `mvn spring-boot:build-image` thành công | Plugin xây được application OCI image | App production đã qua đủ integration/security tests chưa |

Nếu chỉ có CLI nhưng daemon không chạy, `docker --version` vẫn có thể in version. Vì vậy **không được dùng riêng lệnh này để quyết định môi trường đã sẵn sàng**.

### 2.2. Spring Boot plugin có cần Docker CLI không?

Spring Boot 3.5 Maven/Gradle plugins có thể đọc **Docker CLI config files/context**, rồi giao tiếp với **Docker-compatible API**. Chúng không chỉ gọi shell command `docker build`. Docker CLI rất hữu ích để chẩn đoán, nhưng thứ cần thiết là **API daemon có thể truy cập bởi chính build process**, cùng những khả năng cần cho CNB.

Không nhầm `docker buildx version` với probe phù hợp cho Spring Boot `build-image`. Buildx là tooling khác; có Buildx không chứng minh Spring Boot plugin kết nối đúng daemon.

## 3. Điều kiện tối thiểu trước khi gọi build-image

- Có JDK tương thích Java 17 và Spring Boot 3.5.
- Project `mvn clean verify` hoặc `./gradlew clean test bootJar` chạy thành công **không phụ thuộc Docker**.
- Có Docker Engine, Docker Desktop hoặc compatible engine đã chạy và expose API hợp lệ.
- Process Maven/Gradle có quyền truy cập daemon endpoint.
- Daemon có storage, memory và khả năng tạo containers/volumes.
- Mạng/registry hoặc image cache cho phép lấy builder và run images.
- Trên Windows Docker Desktop, dùng **Linux containers** với Paketo Linux builder.
- Image OS/architecture phù hợp: thường Linux `amd64` hoặc `arm64` tùy builder.
- Nếu remote/CI dùng TLS, certificates và firewall/VPN đã cấu hình đúng.

Làm theo thứ tự: **Java project OK → daemon reachable → container capability OK → builder/run image pull OK → build-image OK → run application image OK**. Không đảo ngược thứ tự rồi gộp mọi lỗi thành “Docker lỗi”.

## 4. Kiểm Docker daemon từ terminal

### 4.1. Nấc đầu: CLI có mặt không?

~~~bash
docker --version
~~~

Ví dụ terminal có thể in:

~~~text
Docker version <server-or-cli-version>, build <build-id>
~~~

Dòng trên là **sơ đồ output**, không phải một kết quả thực tế bảo đảm giống mọi máy. Dù lệnh exit code 0, bạn **chưa chứng minh daemon reachable**.

### 4.2. Nấc quan trọng: Docker Server có phản hồi?

~~~bash
docker version
docker info
~~~

`docker version` phải có thông tin **Client** và **Server**. Nếu chỉ Client rồi hiện `Cannot connect to the Docker daemon`, kiểm process daemon, endpoint, context, quyền socket hoặc TLS.

`docker info` thường hiển thị operating system, architecture, container runtime, storage driver, server version và image/cache information. Muốn rút gọn cho script CI:

~~~bash
docker version --format '{{.Server.Version}}'
docker info --format '{{.OSType}}/{{.Architecture}}'
~~~

Đây là Docker CLI Go templates; không cần đoán version. Nếu CLI đang kết nối sai daemon, kết quả có thể “thành công” nhưng thuộc **daemon khác**, nên vẫn cần kiểm context.

### 4.3. Xác nhận Docker Engine API thực sự dùng được

~~~bash
docker ps
docker image ls
~~~

Hai lệnh này tương đối nhẹ, đọc trạng thái containers/images của daemon đã chọn. Khi chính sách cho phép pull public image và tạo container, dùng probe bổ sung:

~~~bash
docker run --rm hello-world
~~~

`docker run` có tác dụng phụ: tạo container, có thể tải image từ registry. Đừng gọi đó là “kiểm tra read-only”; dùng khi được phép. Nếu thành công, daemon có thể chạy container đơn giản, nhưng **vẫn chưa chứng minh CNB builder image sẽ tải/chạy thành công**.

### 4.4. Luồng probe được đề xuất

~~~text
docker --version
    |
    +-- fail --> Docker CLI thiếu/PATH sai
    |
    v
docker version: có Server?
    |
    +-- không --> daemon service/context/socket/TLS/permission
    |
    v
docker info / docker ps
    |
    +-- fail --> authorization/API compatibility
    |
    v
docker run --rm hello-world (tùy chọn, nếu policy cho phép)
    |
    +-- fail --> container runtime/image pull/network/storage
    |
    v
Maven spring-boot:build-image hoặc Gradle bootBuildImage
    |
    +-- fail --> kiểm builder/run image, buildpack, cache, process env
    |
    v
docker image inspect <đúng-image>:<đúng-tag>
    |
    v
docker run --rm <đúng-image>:<đúng-tag>
~~~

Dấu `<...>` trong sơ đồ là ký hiệu vai trò, không phải lệnh phải copy nguyên. Trong bài thực hành ở dưới, tên và tag cụ thể được cung cấp.

## 5. Chuẩn bị Docker Engine trên Linux

### 5.1. Docker service trên host dùng systemd

Sau khi cài Docker Engine theo tài liệu chính thức:

~~~bash
sudo systemctl status docker
docker version
docker info
~~~

Nếu service tồn tại nhưng dừng, người có quyền quản trị có thể:

~~~bash
sudo systemctl start docker
docker version
~~~

**Không áp dụng `systemctl` vô điều kiện** trên WSL2 thiếu systemd, container runner, rootless daemon hay máy dùng init khác. Trên những môi trường đó daemon có lifecycle riêng.

Unix socket Docker Engine mặc định thường là:

~~~text
unix:///var/run/docker.sock
~~~

Nếu dùng rootless engine hoặc alternate context, endpoint có thể khác. **Đừng đoán socket path từ hệ điều hành mà bỏ qua `docker context inspect`.**

### 5.2. Lỗi permission denied

Ví dụ `docker info` báo không truy cập `/var/run/docker.sock`. Thử có quyền quản trị:

~~~bash
sudo docker info
~~~

Nếu thành công với `sudo` nhưng user bình thường thất bại, daemon có thể đang chạy bình thường và lỗi nằm ở **permission của process hiện tại**.

Quản trị viên có thể cấp group theo chính sách:

~~~bash
sudo usermod -aG docker "$USER"
~~~

Sau đó thường cần logout/login hoặc session mới rồi kiểm:

~~~bash
id -nG
docker info
~~~

**Cảnh báo bảo mật:** user thuộc group `docker` có quyền rất mạnh trên host, có thể gần tương đương root. Không tự thêm mọi developer/CI job vào group đó mà thiếu kiểm soát. **Không dùng `chmod 666 /var/run/docker.sock`** để “sửa nhanh”, vì cho các process khác truy cập daemon.

Có thể cân nhắc rootless Docker hoặc isolated runner khi phù hợp; cũng cần hiểu trade-off về socket path, volumes, container privileges và CNB compatibility.

### 5.3. Rootless Docker socket

Rootless daemon thường dùng đường dẫn theo UID, ví dụ:

~~~text
unix:///run/user/1000/docker.sock
~~~

Đây chỉ là **ví dụ** cho UID 1000; đừng hard-code cho mọi máy. Xem UID và Docker context:

~~~bash
id -u
docker context ls
docker context show
docker context inspect "$(docker context show)"
docker info
~~~

Nếu Maven chạy dưới user khác với user sở hữu rootless socket, nó có thể không kết nối được. Cần cấu hình context/socket cho **đúng service account**, không đổi permission bừa bãi.

## 6. Docker Desktop trên Windows và macOS

### 6.1. Windows + Docker Desktop + WSL2

Quy trình chuẩn:

1. Cài Docker Desktop theo hướng dẫn vendor, kiểm virtualization/WSL2 requirements.
2. Khởi chạy Docker Desktop và xác nhận backend **running**.
3. Chọn **Linux containers** để dùng Paketo builder Linux.
4. Mở PowerShell dưới user chạy công cụ build.
5. Chạy:

~~~powershell
docker --version
docker context ls
docker context show
docker version
docker info
~~~

Docker Desktop có thể tạo context tên `desktop-linux`, nhưng **không nên giả định** nó tồn tại trên mọi máy. Nếu daemon chạy Windows containers, builder/run image Linux có thể fail vì OS/platform không tương thích.

Windows Docker API có thể dùng named pipe:

~~~text
npipe:////./pipe/docker_engine
~~~

Thông thường không cần set `DOCKER_HOST` thủ công với named pipe nếu Docker Desktop/current context đã được plugin nhận biết. Kiểm `docker context inspect` trước khi override.

### 6.2. Phân biệt Windows host và WSL2 shell

Giả sử:

~~~text
Windows PowerShell:
    docker version        --> Server OK
    Maven/Gradle?         --> Không chạy ở đây

WSL2 Ubuntu:
    ./mvnw build-image    --> Thực sự chạy ở đây
    docker info           --> Chưa chắc đã OK
~~~

WSL2 distro có **filesystem, home directory, environment và socket view riêng**. Bật Docker Desktop WSL integration nếu workflow yêu cầu, rồi kiểm `docker info` **ngay trong WSL2 shell**. Kết quả ở Windows host không tự cấp quyền cho WSL2 process.

Tương tự, IDE chạy trên Windows host và Gradle daemon chạy ở WSL/container có thể nhìn Docker config khác; hãy probe ở đúng nơi build tool process thực sự chạy.

### 6.3. macOS + Docker Desktop hoặc Colima

Trên macOS, Docker Desktop cung cấp Linux VM với Docker Engine-compatible API. Sau khi start Desktop:

~~~bash
docker context ls
docker context show
docker version
docker info
~~~

Nếu dùng Colima, kiểm daemon/context do Colima tạo:

~~~bash
docker context ls
docker context inspect colima
~~~

Lệnh thứ hai **chỉ dùng khi context `colima` thực sự có**. Không tự copy socket path từ blog cũ vì nó có thể thay theo user và Colima version. Spring Boot plugin có thể đọc Docker context của CLI hoặc cấu hình endpoint tường minh khi cần.

## 7. Docker context là nguồn sự thật của kết nối

### 7.1. Xem daemon endpoint đang được chọn

Linux/macOS:

~~~bash
docker context ls
docker context show
docker context inspect "$(docker context show)"
~~~

PowerShell:

~~~powershell
docker context ls
docker context show
docker context inspect (docker context show)
~~~

Trong kết quả `inspect`, xem `Endpoints.docker.Host`. Nó có thể là Unix socket, Windows npipe hoặc TCP/TLS endpoint. Nếu có nhiều daemon (Desktop, Colima, minikube, remote), **image store của mỗi daemon là riêng**. Build image vào daemon A không có nghĩa `docker image ls` ở daemon B sẽ thấy nó.

Không in Docker registry credentials hay private certificate keys vào public CI logs. Chỉ cần endpoint/context và lỗi kết nối.

### 7.2. Chọn context cho một lệnh thay vì đổi toàn máy

Khi máy **có** context `desktop-linux`:

~~~bash
docker --context desktop-linux info
~~~

Lệnh dùng context này **chỉ cho một Docker CLI invocation**. Ngược lại:

~~~bash
docker context use desktop-linux
~~~

sẽ thay đổi **default context được lưu vào Docker CLI config**, có thể ảnh hưởng terminal/IDE khác dùng cùng config. Hãy cân nhắc trước khi dùng trong môi trường chia sẻ.

### 7.3. Năm biến môi trường Spring Boot 3.5 hỗ trợ

| Biến | Vai trò |
| --- | --- |
| `DOCKER_CONFIG` | Thư mục Docker CLI config và context definitions; mặc định thường `$HOME/.docker` |
| `DOCKER_CONTEXT` | Tên context để lấy thông tin Docker daemon; **ưu tiên `DOCKER_HOST`** |
| `DOCKER_HOST` | Docker API endpoint: Unix socket, named pipe hoặc TCP host/port |
| `DOCKER_TLS_VERIFY` | Giá trị `1` yêu cầu xác minh TLS khi dùng remote TLS |
| `DOCKER_CERT_PATH` | Đường dẫn chứa CA/certificate/key thích hợp cho Docker API TLS |

Spring Boot Maven `build-image` và Gradle `bootBuildImage` đều có thể đọc Docker CLI config, current context và những biến này. **`DOCKER_CONTEXT` ghi đè `DOCKER_HOST`** theo Spring Boot 3.5 Docker daemon docs.

### 7.4. Kiểm env không lộ secrets

Bash trên Linux/macOS:

~~~bash
printenv DOCKER_CONFIG
printenv DOCKER_CONTEXT
printenv DOCKER_HOST
printenv DOCKER_TLS_VERIFY
docker context show
docker version
~~~

`printenv` có thể exit khác 0 khi biến unset; trong shell `set -e`/CI cần xử lý trường hợp đó nếu các biến được phép không có. Không dùng `env` xuất toàn bộ secret-bearing environment ra public logs.

Windows PowerShell:

~~~powershell
Write-Output "DOCKER_CONFIG=$env:DOCKER_CONFIG"
Write-Output "DOCKER_CONTEXT=$env:DOCKER_CONTEXT"
Write-Output "DOCKER_HOST=$env:DOCKER_HOST"
Write-Output "DOCKER_TLS_VERIFY=$env:DOCKER_TLS_VERIFY"
docker context show
docker version
~~~

Không in password/token registry vào logs. Hãy giữ cách kiểm “chỉ in biến Docker endpoint và cờ TLS” thay vì dump toàn bộ environment.

### 7.5. Nếu muốn bỏ override lỗi trong riêng shell hiện tại

Bash:

~~~bash
unset DOCKER_CONTEXT
unset DOCKER_HOST
docker context show
docker info
~~~

PowerShell:

~~~powershell
Remove-Item Env:DOCKER_CONTEXT -ErrorAction SilentlyContinue
Remove-Item Env:DOCKER_HOST -ErrorAction SilentlyContinue
docker context show
docker info
~~~

**Chỉ làm khi bạn đã xác định những overrides hiện tại bị sai.** Trên CI, remote daemon có thể là thiết kế đúng; xóa biến sẽ khiến job kết nối sai daemon. Đừng sửa global Windows system environment hoặc Docker context persistent của người khác mà chưa hiểu tác động.

## 8. Vì sao terminal Docker OK nhưng Maven/Gradle vẫn FAIL?

### 8.1. Không cùng user hoặc process

Process **thừa hưởng env từ process cha**. Maven được mở từ terminal mới có thể khác Gradle daemon đã chạy từ trước hoặc IDE được mở trước khi cấu hình Docker env.

~~~text
Terminal A: docker info -> OK
     |
     +--> Maven chạy trực tiếp trong terminal A -> có env của A

IDE khởi chạy từ hệ điều hành trước khi đổi env
     |
     +--> Gradle build -> có thể có env cũ

CI job container
     |
     +--> Docker socket host có thể không được mount
~~~

Do đó Docker CLI probe phải diễn ra **trong cùng môi trường/runner/user** thực thi build-image. Một `docker version` OK trên host laptop không chứng minh job container có API access.

### 8.2. Plugin có cấu hình Docker riêng

Spring Boot plugin hỗ trợ `docker.context`, `docker.host`, `docker.tlsVerify`, `docker.certPath` và `docker.bindHostToBuilder`. Nếu build script đã đặt endpoint riêng, đọc đúng plugin configuration và build log, không chỉ nhìn CLI default context.

### 8.3. Một lần kiểm tra đầy đủ từ cùng shell

Maven:

~~~bash
docker context show
docker version
docker info
mvn spring-boot:build-image
docker image ls
~~~

Gradle:

~~~bash
docker context show
docker version
docker info
./gradlew --no-daemon bootBuildImage
docker image ls
~~~

Chỉ chạy Gradle Wrapper khi project thực sự có `gradlew`; nếu không, dùng Gradle đã cài với version tương thích. `--no-daemon` giảm một biến số môi trường cho việc chẩn đoán, không thay thế cấu hình context đúng.

## 9. Maven project Spring Boot 3.5.16 hoàn chỉnh

### 9.1. Cấu trúc project

Đây là một ứng dụng Spring Boot Java 17 **không chạy web server**: nó in một dòng rồi kết thúc. Thiết kế này giúp test đường build image mà không bị ảnh hưởng cổng 8080.

~~~text
cnb-connect-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cnb/
    │   └── CnbApplication.java
    └── test/java/com/example/cnb/
        └── CnbApplicationTest.java
~~~

### 9.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cnb-connect-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <image>
                        <name>cnb-connect-demo:1.0.0</name>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-parent` quản lý plugin/dependency versions của Boot 3.5.16. `spring-boot-maven-plugin` cung cấp goal `build-image`, dùng Cloud Native Buildpacks. `<image><name>...` chỉ quyết định **tên image output trong daemon**; không tự publish lên registry.

**Không cần Dockerfile** và không cần thêm `docker-java` vào app dependencies. Plugin build image từ executable JAR, tự sử dụng CNB builder/run image theo cấu hình của nó.

### 9.3. Java class hoàn chỉnh

Tạo `src/main/java/com/example/cnb/CnbApplication.java`:

~~~java
package com.example.cnb;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CnbApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbApplication.class, args);
    }

    public static String message() {
        return "CNB_DAEMON_OK";
    }

    @Bean
    ApplicationRunner output() {
        return args -> System.out.println(message());
    }
}
~~~

Class này compile với Java 17 và Spring Boot Starter. Khi context khởi tạo, `ApplicationRunner` in:

~~~text
CNB_DAEMON_OK
~~~

Đây là **dòng output do Java code tự in**, không phải khẳng định toàn bộ stdout chỉ có một dòng; Spring Boot có thể thêm startup logs.

### 9.4. JUnit test hoàn chỉnh

Tạo `src/test/java/com/example/cnb/CnbApplicationTest.java`:

~~~java
package com.example.cnb;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CnbApplicationTest {

    @Test
    void messageIsStable() {
        assertEquals("CNB_DAEMON_OK", CnbApplication.message());
    }
}
~~~

Đây là unit test không đòi HTTP server, database hoặc Docker. Vì vậy **`mvn clean verify` pass không đồng nghĩa daemon accessible** — một bài học quan trọng khi tách lỗi build Java và lỗi hạ tầng CNB.

### 9.5. Kiểm build Java trước khi xây image

Từ project root (giả định Maven đã cài):

~~~bash
java -version
mvn -version
mvn clean verify
java -jar target/cnb-connect-demo-1.0.0.jar
~~~

Khi thành công có dòng `CNB_DAEMON_OK`. Nếu project được Spring Initializr tạo và **thực sự có Wrapper**, dùng `./mvnw clean verify` trên POSIX hoặc `.\mvnw.cmd clean verify` trên Windows.

### 9.6. Chạy Maven build-image từ cùng môi trường

~~~bash
docker context show
docker version
docker info
mvn spring-boot:build-image
~~~

Goal `build-image` khi gọi từ CLI sẽ đảm bảo package lifecycle đã chạy cần thiết. Nó giao tiếp với Docker API, pull builder/run image nếu cần, chạy CNB lifecycle và export image.

Đọc logs để phân biệt các giai đoạn:

~~~text
Checking / pulling builder image
Checking / pulling run image
Detecting buildpacks
Analyzing / restoring / building
Exporting image
Build success
~~~

Các dòng trên **chỉ là thứ tự khái niệm**, không phải raw log cố định. Nếu build fail ở bước pull, đừng sửa Java class. Nếu fail trước khi contacting daemon, kiểm context/socket/permissions trước.

### 9.7. Kiểm image trong đúng daemon

~~~bash
docker image ls cnb-connect-demo
docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

Khi container chạy được, Java app sẽ in `CNB_DAEMON_OK`. Nếu image không xuất hiện, kiểm Maven image name/tag và Docker context **sau build** có còn trỏ đúng daemon không. Nếu Maven build ở remote Docker daemon nhưng CLI đang đọc Docker Desktop local, hai image stores là khác nhau.

### 9.8. Windows PowerShell tương đương

~~~powershell
docker context show
docker version
docker info
mvn clean verify
mvn spring-boot:build-image
docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

Nếu chưa có Maven trên Windows nhưng project có `mvnw.cmd`, dùng `.\mvnw.cmd` tương ứng. Quan trọng: **Docker Desktop đang chạy Linux containers**, không phải chỉ icon Docker đang có trên taskbar.

## 10. Gradle Kotlin DSL project tương đương

### 10.1. Project và source

Dùng lại **cùng** `CnbApplication.java` và `CnbApplicationTest.java` ở mục 9 trong một project Gradle riêng:

~~~text
cnb-connect-gradle/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/com/example/cnb/CnbApplication.java
└── src/test/java/com/example/cnb/CnbApplicationTest.java
~~~

### 10.2. settings.gradle.kts hoàn chỉnh

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "cnb-connect-gradle"
~~~

### 10.3. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.testing.Test
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )

    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("cnb-connect-gradle:1.0.0")
}
~~~

Spring Boot Gradle Plugin tạo task `bootBuildImage` khi áp dụng Java/War plugin thích hợp. `platform(...)` nhập Spring Boot BOM để versions của Spring libraries/test libraries được quản lý; **chỉ apply Boot plugin không tự đồng nghĩa mọi versionless dependency đã có version**.

### 10.4. Test và xây image

Nếu project có Gradle Wrapper:

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -jar build/libs/cnb-connect-gradle-1.0.0.jar

docker version
docker info
./gradlew --no-daemon bootBuildImage

docker image inspect cnb-connect-gradle:1.0.0
docker run --rm cnb-connect-gradle:1.0.0
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
docker version
docker info
.\gradlew.bat --no-daemon bootBuildImage
docker image inspect cnb-connect-gradle:1.0.0
docker run --rm cnb-connect-gradle:1.0.0
~~~

Các lệnh Wrapper chỉ đúng nếu repo đã có scripts `gradlew`/`gradlew.bat` và `gradle/wrapper/*`. Nếu không, dùng Gradle đã cài với version tương thích để sinh Wrapper rồi chạy. Dòng Java app in sau start là `CNB_DAEMON_OK`.

### 10.5. Gradle Daemon và biến môi trường

Gradle Daemon có thể sống lâu hơn terminal/IDE, làm việc chẩn đoán inherited environment khó hơn. Khi nghi Daemon dùng context/env cũ, thử `--no-daemon` trong đúng shell:

~~~bash
docker context show
docker info
./gradlew --no-daemon bootBuildImage
~~~

Khi cần quản lý daemons của **chính user/project**, có thể dùng `./gradlew --stop`. Đừng dừng shared CI daemons tùy tiện hoặc nghĩ `--no-daemon` thay thế một Docker API endpoint đúng.

## 11. Cấu hình Docker context/endpoint ngay trong Maven Plugin

### 11.1. Mặc định không cần cấu hình host

Trong Docker Desktop hoặc Docker Engine local có current context hợp lệ, Spring Boot Maven Plugin **tự đọc Docker CLI config**. Đặt `<docker><host>...` tường minh chỉ khi có yêu cầu: remote daemon, rootless socket, Colima/Podman hoặc CI đặc biệt.

### 11.2. Chọn một named context

Đoạn nằm trong `spring-boot-maven-plugin` (không phải POM độc lập):

~~~xml
<configuration>
    <docker>
        <context>desktop-linux</context>
    </docker>
</configuration>
~~~

**Chỉ dùng khi `desktop-linux` thực sự tồn tại** với user chạy Maven (`docker context ls`). Một POM chia sẻ trong team thường không nên hard-code context laptop của một thành viên.

### 11.3. Remote Docker daemon có TLS

Ví dụ cấu hình **mô hình**, không phải endpoint đang hoạt động:

~~~xml
<configuration>
    <docker>
        <host>tcp://192.0.2.10:2376</host>
        <tlsVerify>true</tlsVerify>
        <certPath>/home/developer/.docker/certs</certPath>
    </docker>
</configuration>
~~~

`192.0.2.10` là **địa chỉ TEST-NET dùng làm ví dụ tài liệu**, không phải server để kết nối. Khi triển khai thực tế phải có daemon chạy TLS, certificates được cấp, firewall/VPN và path chỉ đúng trong runner. **Không commit private keys** hoặc credentials vào POM.

Đừng dùng `tcp://0.0.0.0:2375` không TLS làm giải pháp chẩn đoán chung: Docker API có quyền rất cao trên host.

### 11.4. bindHostToBuilder

Maven Plugin còn có `bindHostToBuilder`: khi bật, host configuration được cung cấp cho container CNB builder. Tùy chọn này hữu ích với **một số môi trường alternative engines như Podman**, không phải mặc định phải bật với mọi Docker Desktop.

Nếu host API probe pass nhưng builder lifecycle fail do socket/endpoint inside builder, kiểm tài liệu đúng engine rồi mới bật. Không dùng nó để che lỗi permission Docker socket của chính Maven process.

## 12. Cấu hình Docker endpoint trong Gradle

### 12.1. Chọn named context

Snippet bổ sung trong `build.gradle.kts`:

~~~kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    docker {
        context.set("desktop-linux")
    }
}
~~~

Nó cần import `BootBuildImage` như file hoàn chỉnh ở mục 10. Nếu tên context không có trên máy/runner, phải chọn context thật; không commit tên context riêng laptop vào một project dùng chung.

### 12.2. Remote TLS endpoint

Snippet Kotlin DSL:

~~~kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    docker {
        host.set("tcp://192.0.2.10:2376")
        tlsVerify.set(true)
        certPath.set("/home/developer/.docker/certs")
    }
}
~~~

Groovy DSL tương ứng:

~~~groovy
tasks.named("bootBuildImage") {
    docker {
        host = "tcp://192.0.2.10:2376"
        tlsVerify = true
        certPath = "/home/developer/.docker/certs"
    }
}
~~~

Đây là **các ví dụ cấu hình riêng lẻ**, không phải những blocks phải copy đồng thời. Địa chỉ TEST-NET và path minh họa phải được thay bằng values do môi trường thực quản lý. Đừng set cả `context` lẫn `host` khác nhau mà không hiểu precedence; khi debug, chọn **một nguồn cấu hình chính**.

### 12.3. Env variables có thể tốt hơn hard-code

Ở CI, Docker context/TLS thường do runner provision. Dùng env per-job hoặc plugin properties riêng cho runner để tránh hard-code endpoint cá nhân trong build scripts. Quan trọng nhất: environment ấy phải được **Maven/Gradle process** đọc, không chỉ được test trong một terminal không liên quan.

## 13. Daemon connection khác registry connection

### 13.1. docker info OK mà builder pull FAIL

Khi `docker info` chạy thành công, plugin vẫn có thể fail tại:

~~~text
Pulling builder image ...
Pulling run image ...
~~~

Nguyên nhân thường gặp:

- DNS/network/firewall/proxy của daemon không tới registry.
- Registry rate limiting.
- Private registry cần token/password/credential helper.
- Certificates/CA của daemon không trust registry nội bộ.
- Builder/run image tag không tồn tại, registry timeout.
- Image platform không khớp Linux/architecture của daemon.

Đọc **tên image thực từ build log** rồi thử pull trong cùng daemon. Với một project Boot 3.5 dùng Paketo, ví dụ:

~~~bash
docker pull paketobuildpacks/builder-noble-java-tiny:latest
~~~

Đây là image name có thể được plugin 3.5 sử dụng. Không mặc định tag `latest` immutable hay đúng cho mọi release; hãy lấy tên **chính xác từ build log**.

### 13.2. Builder registry và publish registry là hai nhiệm vụ

| Thuộc tính Spring Boot Plugin | Chức năng |
| --- | --- |
| `docker.builderRegistry` | Credentials để pull builder/run images từ registry bảo vệ |
| `docker.publishRegistry` | Credentials để push application image khi publish |
| `docker.host` | Docker daemon API endpoint; không phải registry endpoint |
| `image.name` hoặc Gradle `imageName` | Tên/tag của application image |
| `image.publish` hoặc Gradle `publish` | Yêu cầu publish image (nếu được bật) |

Có thể dùng Docker CLI credential store hoặc helper phù hợp thay vì chèn mật khẩu vào POM/Gradle file. **Không nhầm `docker login` với khởi động daemon**: login chỉ xác thực registry; daemon vẫn cần chạy và kết nối được.

### 13.3. Image ở daemon A không có ở daemon B

Nếu Maven build với remote Docker host nhưng shell hiện chuyển về local Desktop daemon, `docker image ls cnb-connect-demo` có thể không thấy image. Điều này **không khẳng định Maven build thất bại**. Cần giữ cùng context/host khi:

~~~bash
docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

Muốn chuyển image giữa daemons, dùng registry push/pull hoặc image save/load theo quy trình tổ chức; **không tự cho rằng Docker contexts chia sẻ local image store**.

## 14. Builder container, volumes, cache và network

### 14.1. Plugin phải làm nhiều việc hơn docker ps

Cloud Native Buildpacks có thể:

1. Pull builder image và run image.
2. Kiểm builder metadata, image OS/architecture.
3. Tạo container chạy lifecycle.
4. Mount application source/archive, launch/build cache và workspace.
5. Chạy detect/build/export phases của buildpacks.
6. Export OCI image vào daemon image store, tùy cấu hình có thể push registry.

Vì vậy `docker ps` pass nhưng **disk full**, volume mount denied hoặc builder network blocked vẫn khiến build-image fail. Hãy phân biệt lỗi theo **giai đoạn trong log**.

### 14.2. Daemon storage và named volumes

Dùng các lệnh đọc trạng thái:

~~~bash
docker volume ls
docker system df
~~~

Named build cache/launch cache volumes thuộc **đúng daemon**. Chuyển sang remote Docker host là chuyển luôn nơi lưu cache, không đem local cache theo. Nếu CI dùng daemon ephemeral mỗi job, builder/run images và cache có thể phải tải lại.

**Không chạy `docker system prune -a --volumes` vô điều kiện** trên máy chung để chữa lỗi. Lệnh này có thể xóa dữ liệu/images/volumes của các projects khác. Khi cần dọn, xác định đúng đối tượng job sở hữu, backups và retention policy.

### 14.3. Proxy, DNS và certificates trong builder

Host Maven có mạng không đảm bảo **CNB builder container** có mạng tới JDK/buildpack downloads. Proxy/CA có thể cần được cấu hình ở Docker daemon và môi trường builder. Không in proxy passwords ra logs hoặc để private certificates trong repository công khai.

Remote Docker daemon còn có vấn đề **bind mount path**: một host path trên laptop không mặc định tồn tại trên server remote. Khi có custom builder bindings/cache paths, hiểu đường dẫn được giải quyết **trên host daemon** và kiểm quyền ở host đó.

## 15. Các Docker-compatible engines khác

### 15.1. Podman

Spring Boot 3.5 hỗ trợ giao tiếp với Podman khi cấu hình Docker-compatible API phù hợp. Rootless Podman socket thường mang path theo user, ví dụ:

~~~text
unix:///run/user/1000/podman/podman.sock
~~~

Số 1000 chỉ là ví dụ UID; path thực phải được kiểm trên host. Podman CLI có thể hỗ trợ:

~~~bash
podman info --format '{{.Host.RemoteSocket.Path}}'
~~~

Nếu socket/service chưa start hoặc user không có quyền, Spring Boot plugin sẽ fail. Một số trường hợp Podman cần `bindHostToBuilder=true` để cung cấp daemon endpoint tới CNB builder. Kiểm docs và builder logs thay vì áp dụng tùy chọn đó với mọi engine.

### 15.2. Colima

Trên macOS, Colima có Docker-compatible context/socket. Khi `docker context ls` có context `colima` và Colima đang chạy:

~~~bash
docker context inspect colima
docker --context colima info
~~~

Sau đó đặt Docker context/env tương ứng cho Maven/Gradle. Không copy một Unix socket path cố định giữa máy của hai developers.

### 15.3. Minikube và remote Docker

Minikube có thể cung cấp Docker daemon trong VM. Khi dùng `minikube docker-env` hoặc context remote, application image được xây **trong daemon của Minikube**, không tự xuất hiện trong Docker Desktop local. TLS certs, endpoint, image platform và network phải tương thích.

Với một remote Docker daemon qua TCP/TLS, đảm bảo kết nối từ Maven/Gradle **và** các hoạt động buildpack liên quan, không chỉ khả năng SSH đến server. API permissions và image registry traffic phải được quản lý.

## 16. Kiểm trong CI: probe chính xác process sẽ build

### 16.1. Script Maven preflight (Linux shell)

Giả định runner **đã có JDK, Docker CLI, daemon API và Maven Wrapper do project cung cấp**, không cần script tự cài công cụ:

~~~bash
set -eu

java -version
./mvnw -version
docker context show
docker version
docker info --format '{{.OSType}}/{{.Architecture}}'

./mvnw -B -ntp clean verify
./mvnw -B -ntp spring-boot:build-image

docker image inspect cnb-connect-demo:1.0.0
docker run --rm cnb-connect-demo:1.0.0
~~~

Bài Maven tự tạo trước đó **không mặc định có Wrapper**, nên script này là mẫu CI cho trường hợp repository đã sinh/commit `mvnw`. Nếu chưa có Wrapper, dùng Maven đã cài với version được kiểm soát.

### 16.2. Script Gradle preflight

~~~bash
set -eu

java -version
./gradlew --version
docker version
docker info --format '{{.OSType}}/{{.Architecture}}'

./gradlew --no-daemon clean test bootJar
./gradlew --no-daemon bootBuildImage

docker image inspect cnb-connect-gradle:1.0.0
docker run --rm cnb-connect-gradle:1.0.0
~~~

CI phải dùng **cùng daemon** xuyên suốt các bước build và inspect. Không gọi `docker context use` ở một bước rồi ngầm mong job khác/container khác cùng nhận thay đổi; xác định context/host trong runner configuration.

### 16.3. Các mô hình runner

| Runner | Docker daemon thường nằm ở đâu? | Rủi ro cần kiểm |
| --- | --- | --- |
| Linux VM self-hosted | Local `dockerd` system service | Permissions, disk, lifecycle |
| Docker Desktop self-hosted | Desktop VM/WSL backend | User session, Linux containers mode |
| Job container + host Docker socket | Host daemon bên ngoài container | Mount socket cho quyền mạnh lên host |
| Docker-in-Docker (DinD) | Service container có daemon riêng | TLS, privileged mode, network, cache |
| Remote API daemon | VM/host chuyên dụng | TLS, firewall, certificates, host path semantics |
| Rootless Docker/Podman | Daemon per-user/socket riêng | UID, socket lifetime, CNB compatibility |

**Không khuyến nghị cổng TCP 2375 không TLS** cho mọi CI chỉ vì dễ cấu hình. Nếu tổ chức dùng DinD hoặc remote daemon, cần runner isolation và TLS/auth theo tiêu chuẩn bảo mật, tránh cho untrusted PR code quyền Docker host API rộng.

### 16.4. Phân định lỗi theo tầng

~~~text
Tầng 1: Java/compiler/test -> mvn clean verify / gradle clean test
Tầng 2: Docker API        -> docker version / docker info
Tầng 3: Container runtime -> docker ps / docker run smoke
Tầng 4: Registry          -> pull builder/run images
Tầng 5: Buildpacks        -> detect / build / export logs
Tầng 6: Image store       -> docker image inspect
Tầng 7: App runtime       -> docker run + readiness/business tests
Tầng 8: Publishing        -> registry auth/push/digest
~~~

Một tầng pass không chứng minh các tầng sau pass; đó là lý do CI nên fail ở bước đầu tiên nêu rõ vấn đề, không chỉ có một lệnh build-image bao trùm mọi chẩn đoán.

## 17. Troubleshooting theo triệu chứng

| Lỗi nhìn thấy | Nguyên nhân khả dĩ | Hướng xác nhận/sửa |
| --- | --- | --- |
| `docker: command not found` | CLI chưa cài/PATH sai | Cài Docker CLI/Engine hợp lệ, kiểm PATH |
| `docker --version` OK, `docker version` không có Server | Daemon dừng, context sai, endpoint unreachable | Khởi động daemon, kiểm context/socket |
| `Cannot connect to Docker daemon at unix:///var/run/docker.sock` | Socket không có hoặc process không truy cập được | Kiểm daemon service, current context, rootless path |
| `permission denied while trying to connect to docker.sock` | User/group thiếu quyền API | Cấp quyền được phê duyệt, không chmod 666 |
| `sudo docker info` OK, thường fail | Daemon OK nhưng ordinary user thiếu socket permission | Xem group/session/rootless options |
| Docker Desktop Windows chạy Windows containers | Paketo builder là Linux image | Chuyển Linux containers, kiểm Docker Server OS |
| Host Docker OK nhưng WSL/IDE Maven fail | Khác process/home/socket/env | Kiểm trực tiếp trong WSL/IDE runner process |
| `DOCKER_CONTEXT` và `DOCKER_HOST` khác nhau | Env precedence gây trỏ nhầm daemon | Giữ nguồn cấu hình chính, kiểm context inspect |
| Docker TLS handshake failure | CA/cert path, endpoint TLS, firewall | Kiểm certificate/host/TLS, không tắt security |
| Docker TCP connection refused | Daemon không listen trên endpoint hoặc network chặn | Xem server listeners/firewall/VPN |
| CLI `docker info` OK nhưng Boot plugin fail | POM/Gradle docker context/host override hoặc process khác env | Xem plugin config, user và runner environment |
| Pull builder image bị unauthorized | Registry cần credentials | Kiểm image name, credential helper/builderRegistry |
| Pull builder image timeout | DNS/proxy/firewall/registry rate limit | Thử `docker pull` đúng image, kiểm daemon network |
| `no matching manifest for linux/...` | Image architecture/OS không tương thích | Chọn compatible builder/platform và daemon mode |
| Builder chạy nhưng Java download fail | CNB builder network/CA/proxy | Xem lifecycle logs và builder env |
| Build lỗi volume/cache mount | Disk, user rights, remote path mismatch | Kiểm `docker system df`, named volumes/bind mounts |
| Maven Java tests fail trước image build | Source/compiler/dependency lỗi | Sửa `mvn clean verify` trước Docker |
| Gradle `bootBuildImage` task không có | Chưa apply Java/War hoặc Boot plugin đúng | Kiểm Gradle plugins và `tasks` |
| Image build success nhưng `docker image ls` không thấy | Docker CLI đang nhìn daemon khác | So context/DOCKER_HOST của plugin và CLI |
| Image có nhưng `docker run` báo ClassNotFound | App packaging/classpath issue | Chạy `java -jar`, xem dependencies/Boot JAR |
| Publish fail `denied` sau khi build local OK | Registry push credentials/permissions | Kiểm publishRegistry/login/tag, không đổi daemon |
| Docker socket mounted vào untrusted PR job | Security isolation yếu | Dùng trusted isolated runner/remote managed build service |
| CI build chậm sau mỗi job | Daemon ephemeral, mất image/cache volumes | Cân nhắc cache image/volume theo chính sách |
| Có `docker buildx` nhưng CNB fail | Buildx không xác nhận API của plugin | Chẩn đoán `bootBuildImage` Docker context và Engine API |

### 17.1. Quy trình debug năm bước

**Bước 1:** Xác định **terminal, IDE, WSL distro, container hoặc CI job** nào thật sự chạy Maven/Gradle.

**Bước 2:** Kiểm **Docker context/env/plugin config** trỏ daemon nào; không đổi đồng thời nhiều endpoints.

**Bước 3:** Dùng `docker version` có Server, `docker info` và `docker ps` trong môi trường tương ứng; nếu fail, giải quyết daemon API trước.

**Bước 4:** Nếu API pass, đọc build-image log để xác định fail ở registry pull, builder lifecycle, cache, export hay publishing.

**Bước 5:** Khi image build thành công, dùng **cùng context** với tên/tag chính xác để `docker image inspect` và `docker run`, kiểm Java app output và hành vi vận hành thực.

## 18. Bài tập kèm đáp án

**Bài 1 — CLI đã cài nhưng daemon chưa xác nhận.** `docker --version` in version, `docker version` báo chỉ có Client.  
**Đáp án:** Chưa kết nối daemon; kiểm service, context, socket, TLS/permissions. Chưa nên sửa Java source.

**Bài 2 — Docker context ưu tiên.** `DOCKER_CONTEXT` trỏ remote daemon, `DOCKER_HOST` trỏ Unix socket local.  
**Đáp án:** Spring Boot 3.5 docs quy định `DOCKER_CONTEXT` ưu tiên. Nên giữ một nguồn endpoint nhất quán.

**Bài 3 — Maven tests pass nhưng build-image fail.**  
**Đáp án:** Tests là Java build/test path; CNB image build thêm daemon, builder, registry và container lifecycle. Probe `docker version`/`info` trước.

**Bài 4 — Linux user permission.** `sudo docker info` OK nhưng `docker info` fail.  
**Đáp án:** User thường thiếu quyền socket; xử lý account/runner permissions theo security policy, không chmod 666.

**Bài 5 — Windows Linux containers.** Docker Desktop chạy Windows containers, Paketo builder pull báo OS mismatch.  
**Đáp án:** Chọn Linux containers mode và kiểm Server OSType/architecture.

**Bài 6 — Remote image store.** Maven build image thành công trên remote daemon, nhưng local Docker Desktop không thấy image.  
**Đáp án:** Daemons có stores khác nhau. Inspect/run với đúng remote context hoặc publish/pull qua registry.

**Bài 7 — Registry auth khác daemon auth.** `docker info` pass, pull builder fail `unauthorized`.  
**Đáp án:** Docker API đã reachable; kiểm builder registry credentials/permissions và `docker.builderRegistry`, không đổi `DOCKER_HOST`.

**Bài 8 — Maven vs Gradle task.** Tên lệnh chuẩn nào được Spring Boot dùng?  
**Đáp án:** Maven `spring-boot:build-image`; Gradle `bootBuildImage`. Cả hai dùng CNB, không cần Dockerfile.

**Bài 9 — Output project demo.** Khi chạy Maven hoặc Gradle image mẫu thành công, Java code in gì?  
**Đáp án:** `CNB_DAEMON_OK`, ngoài các startup logs khác.

**Bài 10 — Docker socket của untrusted CI.** Có nên mount `/var/run/docker.sock` cho mọi PR job?  
**Đáp án:** Không. Docker API có quyền rất mạnh; dùng runner isolated/trusted hoặc hạ tầng container build được quản lý.

## 19. Checklist nghiệm thu môi trường

- [ ] Java/toolchain phù hợp; Maven/Gradle project compile và test pass trước.
- [ ] Docker Engine/Desktop/container engine daemon thực sự chạy.
- [ ] `docker version` có **Server**, không chỉ `docker --version`.
- [ ] `docker info` và `docker ps` pass dưới **user/job chạy build**.
- [ ] Docker context và `DOCKER_CONTEXT`/`DOCKER_HOST`/`DOCKER_CONFIG` nhất quán.
- [ ] Không có POM/Gradle `docker.context` hoặc `docker.host` override trỏ nhầm daemon.
- [ ] Docker Desktop Windows dùng Linux containers với builder Linux.
- [ ] Engine có đủ resources và quyền tạo containers, images, cache volumes.
- [ ] Có đường pull builder/run image hoặc registry proxy/cache đúng.
- [ ] Registry credentials/proxy/TLS trust được quản lý tách khỏi Docker daemon access.
- [ ] Remote Docker API dùng TLS và firewall; không mở TCP 2375 public.
- [ ] Docker socket không bị mở cho untrusted users/jobs.
- [ ] `spring-boot:build-image` hoặc `bootBuildImage` chạy từ đúng project/build tool.
- [ ] Image cuối được kiểm bằng `docker image inspect` trên cùng daemon.
- [ ] `docker run --rm` khởi động app; demo in `CNB_DAEMON_OK`.
- [ ] CI ghi đủ thông tin version/context/error phase để chẩn đoán.
- [ ] Không dùng `docker system prune -a --volumes` làm cách sửa lỗi chung.
- [ ] Có chính sách pin builder/runtime images, scan và lưu image digest khi release.

## 20. Nguồn chính thức

- Spring Boot 3.5 Maven — Packaging OCI Images và Docker Daemon: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Spring Boot 3.5 Gradle — Packaging OCI Images, bootBuildImage: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html
- Spring Boot Wiki — Building OCI Images, Docker-compatible engines: https://github.com/spring-projects/spring-boot/wiki/Building-OCI-Images-with-Spring-Boot
- Docker CLI Reference — context/host/environment options: https://docs.docker.com/reference/cli/docker/
- Docker Contexts: https://docs.docker.com/engine/manage-resources/contexts/
- Docker Context Use: https://docs.docker.com/reference/cli/docker/context/use/
- Docker Engine Linux post-install and permissions: https://docs.docker.com/engine/install/linux-postinstall/
- Docker Desktop Windows installation: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker Engine daemon socket: https://docs.docker.com/reference/cli/dockerd/#daemon-socket-option
- Cloud Native Buildpacks documentation: https://buildpacks.io/docs/
- Paketo Buildpacks: https://paketo.io/docs/

**Kết luận:** Để Spring Boot tạo OCI image bằng Buildpacks, **Maven/Gradle process phải truy cập được Docker-compatible daemon**, không chỉ có Docker CLI trên PATH. Chuỗi kiểm chứng đáng tin cậy là `docker version` có Server → `docker info` trong đúng user/context → plugin `build-image`/`bootBuildImage` → `docker image inspect` → `docker run`. Nếu fail, phân loại lỗi API, permissions, registry, builder lifecycle và app runtime thay vì thay cấu hình Java hoặc Docker endpoint một cách ngẫu nhiên.