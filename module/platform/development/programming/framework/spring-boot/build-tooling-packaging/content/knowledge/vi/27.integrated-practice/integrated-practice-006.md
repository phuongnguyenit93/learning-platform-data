# Tạo image bằng Dockerfile và Buildpacks từ cùng một ứng dụng Spring Boot

## 1. Mục tiêu: một ứng dụng, hai cách tạo OCI image

Một ứng dụng Spring Boot có thể được đóng gói thành container image theo ít nhất hai cách phổ biến:

- **Dockerfile:** nhóm phát triển mô tả tường minh base image, các lệnh cài đặt/copy, user, port và entrypoint. Docker BuildKit thực hiện những chỉ dẫn đó để tạo image.
- **Cloud Native Buildpacks (CNB):** nhóm phát triển đưa source code hoặc executable archive cho một builder. Buildpacks tự phát hiện loại ứng dụng, chọn các buildpacks phù hợp, chuẩn bị runtime và tạo OCI image theo lifecycle.

Cả hai phương pháp đều có thể tạo OCI image chạy cùng một ứng dụng. Khác biệt nằm ở mức kiểm soát, cách tạo layer, cách chọn JRE, quy trình cập nhật base image, khả năng tùy chỉnh và lượng cấu hình nhóm phát triển phải duy trì.

Bài thuộc mục **Thực hành tổng hợp** trong chủ đề **Spring Boot Build Tooling Packaging**. Sau bài này, bạn có thể:

1. Giải thích Dockerfile, multi-stage build, Buildpack, builder, build image, run image và CNB lifecycle.
2. Tạo một ứng dụng Spring Boot Java 17 có endpoint kiểm tra sức khỏe.
3. Build executable JAR đúng một lần, lưu SHA-256 và dùng chính archive đó làm đầu vào cho cả hai phương pháp.
4. Viết Dockerfile chạy JAR trên JRE 17 bằng non-root user.
5. Dùng Paketo Buildpacks CLI `pack` tạo image từ executable JAR đã build.
6. Dùng Spring Boot Maven Plugin `spring-boot:build-image` để tạo image trực tiếp từ Maven project.
7. Chạy hai image trên hai port khác nhau và xác nhận cùng một HTTP response.
8. Kiểm tra image metadata, runtime Java, user, layers, image size và registry digest.
9. So sánh caching, khả năng tùy chỉnh, bảo mật, reproducibility, debugging và bảo trì.
10. Chọn cách đóng gói phù hợp và đưa cả hai phương pháp vào CI/CD có kiểm soát.

**Bộ thực hành:** Java `17`, Spring Boot `3.5.16`, Maven, Docker Engine/BuildKit, Cloud Native Buildpacks, Paketo builder và Pack CLI. Hai image mẫu dùng tên:

~~~text
local/image-build-comparison:dockerfile
local/image-build-comparison:buildpacks
~~~

Đây là tag local cho bài lab, không phải tên registry để phát hành. Các lệnh build trong bài cần Docker daemon hoạt động và có quyền pull builder/base images.

## 2. Hai phương pháp giải quyết cùng một bài toán

### 2.1. Dockerfile

Dockerfile là một bản mô tả các bước Docker cần thực hiện. Ví dụ một image Java có thể khai báo:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY application.jar /app/application.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Nhóm phát triển tự quyết định:

- Base image và phiên bản JRE.
- File nào được đưa vào image.
- User/group và quyền truy cập filesystem.
- Environment variables, port metadata, healthcheck và entrypoint.
- Các package hệ điều hành cần thiết.
- Cách chia layer và cách cache các bước build.

Dockerfile đem lại quyền kiểm soát trực tiếp. Đổi lại, nhóm phát triển chịu trách nhiệm cập nhật base image, giữ runtime an toàn, xử lý quyền file, cấu hình JVM và duy trì các bước build.

### 2.2. Cloud Native Buildpacks

Buildpacks tự động hóa quá trình chuyển source hoặc application archive thành OCI image. Một **builder** là image chứa:

- Các buildpacks theo thứ tự.
- Lifecycle binaries điều phối build.
- Build image làm môi trường thực hiện build.
- Metadata tham chiếu run image dùng làm nền runtime.

Buildpack kiểm tra ứng dụng, tạo build plan và đóng góp các layer cần thiết. Với ứng dụng Java, Paketo có thể nhận diện Maven/Gradle, executable JAR, WAR và chọn buildpacks phù hợp.

Nhóm phát triển có thể tập trung vào source code, Maven/Gradle metadata và các cấu hình như `BP_JVM_VERSION`. Builder quyết định nhiều chi tiết runtime/layer theo buildpack versions và cấu hình của nó.

### 2.3. Không có một image “chuẩn” giống nhau cho cả hai cách

Cùng một JAR đầu vào không làm hai image có cùng digest. Hai phương pháp có thể sử dụng:

- Base OS và JRE patch khác nhau.
- Image config, user, entrypoint và labels khác nhau.
- Layer boundaries và compression khác nhau.
- Buildpack metadata, SBOM và process types khác nhau.
- Thời điểm tạo image, architecture và manifest khác nhau.

Mục tiêu so sánh là xác nhận **cùng một ứng dụng, cùng một JAR đầu vào, cùng contract runtime và cùng kết quả smoke test**. Không lấy việc hai digest khác nhau làm bằng chứng một image sai.

## 3. Hiểu Buildpacks lifecycle

Cloud Native Buildpacks không chỉ là một lệnh tự động viết Dockerfile. Builder chạy một lifecycle để phát hiện, xây dựng và xuất image.

Luồng khái quát:

~~~text
Executable JAR / source
          |
          v
      ANALYZE
  đọc metadata image cũ
          |
          v
       DETECT
  chọn buildpacks phù hợp
          |
          v
       RESTORE
  phục hồi các cached layers
          |
          v
        BUILD
  thực thi buildpacks
          |
          v
       EXPORT
  tạo OCI image + cache
          |
          v
      RUN IMAGE
  launcher chạy process
~~~

| Phase | Vai trò |
| --- | --- |
| Analyze | Đọc metadata image trước đó để xác định layer có thể tái sử dụng |
| Detect | Chạy detection của buildpacks và chọn build plan |
| Restore | Khôi phục các layer đã cache |
| Build | Thực thi các buildpacks được chọn để tạo/contribute layer |
| Export | Lắp ráp image và lưu metadata/cache |

Khi chạy ứng dụng, CNB launcher gọi process type đã được buildpack đóng góp. Với Java executable JAR, Paketo thường cung cấp các process type như `web`, `task` và `executable-jar`.

Một builder có thể gồm nhiều buildpacks; không phải mọi buildpack trong builder đều nhất thiết đóng góp layer cho mọi ứng dụng. Detection xác định buildpacks phù hợp với project.

## 4. Cấu trúc project thực hành

Tạo project:

~~~text
image-build-comparison/
  pom.xml
  Dockerfile
  .dockerignore
  src/
    main/
      java/
        demo/
          ImageBuildComparisonApplication.java
  target/
    image-build-comparison-1.0.0.jar
  dist/
    application.jar
~~~

`target/` là output Maven. `dist/application.jar` là bản copy được dùng làm **đầu vào chung** cho hai cách tạo image.

Bài thực hành build JAR một lần rồi:

1. Dockerfile copy `dist/application.jar` vào runtime image.
2. Pack CLI dùng chính `dist/application.jar` làm application path để Buildpacks phát hiện executable JAR.

Như vậy cả hai phương pháp nhận cùng bytes của executable archive. Dockerfile giữ file JAR trong filesystem image; Java Buildpack xử lý archive thành application contents/layers trong image.

## 5. pom.xml: Spring Boot Java 17

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.container</groupId>
    <artifactId>image-build-comparison</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Image Build Comparison</name>
    <description>One Spring Boot app packaged by Dockerfile and Buildpacks</description>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.target>17</maven.compiler.target>
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
                <configuration>
                    <image>
                        <name>local/image-build-comparison:buildpacks-maven</name>
                        <builder>paketobuildpacks/builder-noble-java-tiny:latest</builder>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                            <BP_JVM_TYPE>JRE</BP_JVM_TYPE>
                        </env>
                        <publish>false</publish>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `spring-boot-starter-parent` quản lý phiên bản plugin/dependency tương thích với Spring Boot 3.5.16.
- `java.version` và `maven.compiler.release` đặt baseline compile Java 17.
- `maven.compiler.target` cũng được khai báo rõ để công cụ Buildpacks nhận diện target Java thông qua compiler configuration/target metadata.
- `spring-boot-starter-web` cung cấp Spring MVC và embedded servlet container.
- `image.name` xác định tag cho đường build bằng Spring Boot Maven Plugin.
- `builder` chọn Paketo builder cụ thể. Tag `latest` tiện cho lab nhưng có thể thay đổi theo thời gian.
- `BP_JVM_VERSION=17` yêu cầu Paketo Java Buildpack cài JVM major 17.
- `BP_JVM_TYPE=JRE` chọn JRE cho runtime image; buildpack vẫn có thể dùng JDK ở build-time.
- `publish=false` giữ image ở local Docker daemon, không upload registry.

Trong production, thay builder tag mutable bằng image digest đã được kiểm duyệt, pin plugin/buildpack versions và kiểm soát JVM patch/provider theo chính sách cập nhật. `BP_JVM_VERSION=17` khóa major release; nó không tự pin mọi patch version của JRE.

## 6. Application.java: một endpoint dùng chung để so sánh

Tạo `src/main/java/demo/ImageBuildComparisonApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ImageBuildComparisonApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ImageBuildComparisonApplication.class, args);
    }

    @GetMapping(value = "/health", produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "image-build-comparison:ok";
    }
}
~~~

Ứng dụng mở HTTP endpoint `GET /health` trên port mặc định `8080`. Cả hai images phải trả đúng cùng một response body.

Đây là một ví dụ Spring Boot độc lập, không cần database, message broker hoặc external service. Điều này giúp tập trung vào cách đóng gói image và loại bỏ biến số từ hệ thống phụ trợ.

## 7. Build JAR đúng một lần

Từ project root, chạy:

~~~bash
mvn -B -ntp clean verify
~~~

Kiểm tra executable JAR:

~~~bash
test -f target/image-build-comparison-1.0.0.jar
jar tf target/image-build-comparison-1.0.0.jar
~~~

JAR Spring Boot executable thông thường có các entries:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/ImageBuildComparisonApplication.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Kiểm tra main class và dependencies:

~~~bash
unzip -l target/image-build-comparison-1.0.0.jar
~~~

Nếu máy không có `unzip`, dùng `jar tf` của JDK.

Copy archive sang thư mục handoff:

Linux/macOS/Git Bash:

~~~bash
mkdir -p dist
cp target/image-build-comparison-1.0.0.jar dist/application.jar
sha256sum dist/application.jar
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force dist
Copy-Item target/image-build-comparison-1.0.0.jar dist/application.jar
Get-FileHash dist/application.jar -Algorithm SHA256
~~~

Lưu SHA-256 được in ra vào build record. Không tự điền một hash minh họa; mỗi lần build tạo bytes thực tế cần được đo lại.

Có thể chạy JAR trực tiếp trên Java 17 trước khi tạo image:

~~~bash
java -jar dist/application.jar
~~~

Sau đó gọi:

~~~bash
curl -fsS http://localhost:8080/health
~~~

Response body chính xác:

~~~text
image-build-comparison:ok
~~~

Ứng dụng vẫn chạy để phục vụ request; nhấn Ctrl+C khi muốn dừng.

## 8. Dockerfile: đóng gói JAR vào JRE 17

Tạo `Dockerfile` tại project root:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

COPY --chown=10001:10001 dist/application.jar /app/application.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Giải thích từng lệnh:

- `FROM` chọn image JRE 17 làm nền runtime.
- `WORKDIR` đặt thư mục làm việc.
- `COPY --chown` copy đúng JAR đã build và gán ownership cho UID/GID 10001.
- `USER` chạy process bằng numeric non-root identity.
- `EXPOSE` khai báo port ứng dụng dự kiến lắng nghe; lệnh này không tự publish port trên host.
- `ENTRYPOINT` dùng exec form để JVM trở thành process chính và nhận signal từ container runtime.

Dùng numeric UID/GID giúp không cần tạo user name riêng trong image lab. Ứng dụng mẫu không cần ghi vào `/app`. Nếu ứng dụng thực tế cần ghi file, hãy xác định volume/path và cấp quyền tối thiểu cho đúng thư mục đó.

### 8.1. .dockerignore

Tạo `.dockerignore`:

~~~text
.git
.idea
.vscode
target/
build/
**/*.log
.env
.env.*
~~~

Dockerfile chỉ cần `dist/application.jar` và chính file Dockerfile. Loại bỏ source build outputs, IDE files, Git history, logs và environment files khỏi Docker context.

Không thêm `dist/` vào ignore list vì đây là thư mục chứa archive được Dockerfile copy. Cũng không đưa credentials hoặc `.env` vào image build context.

### 8.2. Build Dockerfile image

~~~bash
docker build --pull \
  --file Dockerfile \
  --tag local/image-build-comparison:dockerfile \
  .
~~~

Docker Engine thực hiện Dockerfile instructions và tạo image local. `--pull` yêu cầu kiểm tra/pull base image theo tag; với tag mutable, kết quả có thể thay đổi giữa các lần build.

Trong production, pin base image bằng digest đã được duyệt, đồng thời có lịch cập nhật digest để nhận security fixes. Không dùng một tag như `latest` làm bằng chứng runtime image bất biến.

### 8.3. Kiểm tra Dockerfile image

~~~bash
docker image inspect local/image-build-comparison:dockerfile
docker history --no-trunc local/image-build-comparison:dockerfile
docker image ls local/image-build-comparison
~~~

Xem user đã cấu hình:

~~~bash
docker image inspect --format '{{.Config.User}}' local/image-build-comparison:dockerfile
~~~

Output mong đợi:

~~~text
10001:10001
~~~

Kiểm tra Java runtime:

~~~bash
docker run --rm --entrypoint java local/image-build-comparison:dockerfile -version
~~~

Runtime cần báo Java 17. Patch version và vendor cụ thể phụ thuộc base image tag/digest được kéo tại thời điểm build.

## 9. Buildpacks: tạo image từ đúng JAR đầu vào

Cài Pack CLI và Docker Engine theo hướng dẫn chính thức của Cloud Native Buildpacks. Kiểm tra:

~~~bash
pack version
docker version
docker info
~~~

Docker daemon phải hoạt động và có thể pull builder image. Với đường build này, ta cung cấp `dist/application.jar` làm application path.

Chạy:

~~~bash
pack build local/image-build-comparison:buildpacks \
  --path dist/application.jar \
  --builder paketobuildpacks/builder-noble-java-tiny:latest \
  --env BP_JVM_VERSION=17 \
  --env BP_JVM_TYPE=JRE
~~~

Ý nghĩa:

- `pack build` yêu cầu CNB lifecycle tạo một image.
- `--path dist/application.jar` dùng executable JAR đã được Maven build ở mục 7.
- `--builder` chỉ định builder chứa lifecycle/buildpacks và metadata run image.
- `BP_JVM_VERSION=17` yêu cầu Java Buildpack cung cấp Java 17.
- `BP_JVM_TYPE=JRE` chọn JRE cho runtime.

Buildpack phát hiện executable JAR, chuẩn bị application contents, đóng góp JVM/runtime layers và tạo image. Không cần tự viết một `ENTRYPOINT` Dockerfile cho đường này; executable JAR buildpack đóng góp process type để launcher khởi chạy ứng dụng.

### 9.1. Kiểm tra Buildpacks image

~~~bash
docker image inspect local/image-build-comparison:buildpacks
docker image ls local/image-build-comparison
~~~

Kiểm tra user cấu hình:

~~~bash
docker image inspect --format '{{.Config.User}}' local/image-build-comparison:buildpacks
~~~

CNB images được Spring Boot Build Image documentation mô tả là build/run bằng non-root users vì lý do bảo mật. UID/GID cụ thể phụ thuộc builder/run image; không giả định nó luôn bằng 10001 như Dockerfile mẫu.

Kiểm tra Java:

~~~bash
docker run --rm --entrypoint java local/image-build-comparison:buildpacks -version
~~~

Java major phải là 17 theo cấu hình `BP_JVM_VERSION`. Patch version/provider phụ thuộc buildpack release và dependency metadata.

### 9.2. Cache của Buildpacks

CNB builder có build cache và launch cache cho các layers do buildpacks tạo. Lifecycle có thể phục hồi layers từ image trước/cache rồi chỉ build lại những phần cần thiết.

Không xóa cache sau mỗi build nếu mục tiêu là đo incremental performance. Ngược lại, khi điều tra lỗi cache, có thể build lại với cache được làm sạch bằng option tương ứng của builder/Pack hoặc plugin, nhưng cần ghi rõ đó là clean-cache run.

Cache là cơ chế tối ưu build. Nó không thay image tag/digest, không thay thế registry retention và không chứng minh image đã được security review.

## 10. Đường Buildpacks tích hợp trực tiếp Spring Boot Maven Plugin

Ngoài Pack CLI, Spring Boot Maven Plugin có goal `spring-boot:build-image`. Goal này tạo OCI image bằng Cloud Native Buildpacks và tự chạy package lifecycle để đảm bảo executable archive đã được tạo.

Với POM ở mục 5, chạy:

~~~bash
mvn -B -ntp spring-boot:build-image
~~~

Plugin dùng tên image được cấu hình:

~~~text
local/image-build-comparison:buildpacks-maven
~~~

Đường tích hợp này tiện khi Maven là build orchestrator chính và muốn tạo image ngay sau package. Plugin có thể tự repackage ứng dụng nếu cần; không bắt buộc chạy goal `repackage` riêng trước `build-image`.

### 10.1. Khác biệt giữa Maven plugin route và Pack route

| Cách gọi | Application input | Ai điều phối |
| --- | --- | --- |
| `mvn spring-boot:build-image` | Maven project và executable archive được tạo trong lifecycle | Spring Boot Maven Plugin |
| `pack build --path dist/application.jar` | JAR đã build sẵn | Pack CLI và CNB lifecycle |
| `docker build -f Dockerfile` | File được COPY trong Docker context | Dockerfile instructions và BuildKit |

Maven plugin route thuận tiện và hiểu Spring Boot packaging. Pack route phù hợp khi muốn kiểm soát rõ file archive đầu vào hoặc tích hợp Buildpacks với pipeline không dùng Spring Boot Maven goal.

Trong bài so sánh chính, Pack route sử dụng đúng file `dist/application.jar` mà Dockerfile copy. Maven plugin route là một lựa chọn tích hợp bổ sung; nó chạy Maven package lifecycle và tạo archive từ cùng source project, vì vậy không nên mặc nhiên coi bytes của JAR ở hai lần build là giống hệt.

### 10.2. Docker daemon và registry credentials

Spring Boot `build-image` cần kết nối Docker daemon. Plugin đọc Docker CLI configuration/context hoặc dùng các Docker connection parameters được cấu hình.

Nếu chỉ tạo image local, `publish=false` là đủ. Khi publish registry, cấu hình credentials qua Docker credential helper/secret store hoặc các trường registry configuration được plugin hỗ trợ. Không ghi username/password/token vào POM đã commit.

Nếu builder hoặc run image ở private registry, cung cấp quyền pull cho builder. Quyền pull builder/run image khác quyền push application image; cấp đúng quyền cho từng registry.

### 10.3. build-image-no-fork

Nếu muốn bind image creation vào package lifecycle trong POM, dùng goal `build-image-no-fork`:

~~~xml
<execution>
    <id>build-container-image</id>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

`build-image-no-fork` không fork lifecycle để tự bảo đảm package đã chạy. Nó phù hợp khi được bind vào lifecycle; khi gọi trực tiếp trên command line, dùng `spring-boot:build-image`.

Không bind `build-image` vào package theo cách gây fork lifecycle lặp lại. Xem tài liệu plugin và execution ordering trước khi tự động hóa.

## 11. Chạy cả hai image và kiểm tra cùng HTTP contract

Chạy Dockerfile image:

~~~bash
docker run --detach \
  --name image-dockerfile \
  --publish 18080:8080 \
  local/image-build-comparison:dockerfile
~~~

Chạy Buildpacks image:

~~~bash
docker run --detach \
  --name image-buildpacks \
  --publish 18081:8080 \
  local/image-build-comparison:buildpacks
~~~

Hai container cùng chạy một application, nhưng dùng hai host ports khác nhau.

Kiểm tra endpoint:

~~~bash
curl --fail --silent --show-error --retry 30 \
  --retry-connrefused --retry-delay 1 --retry-max-time 35 \
  http://127.0.0.1:18080/health
~~~

~~~bash
curl --fail --silent --show-error --retry 30 \
  --retry-connrefused --retry-delay 1 --retry-max-time 35 \
  http://127.0.0.1:18081/health
~~~

Cả hai response body phải chính xác:

~~~text
image-build-comparison:ok
~~~

Đây là bằng chứng hai images khởi động ứng dụng và phục vụ cùng endpoint. Nó không chứng minh image có cùng layer contents, digest, JRE patch hoặc security posture.

### 11.1. Dọn container sau bài lab

~~~bash
docker rm --force image-dockerfile image-buildpacks
~~~

Nếu tên container đã được dùng bởi một bài chạy trước, kiểm tra đúng container trước khi xóa. Không xóa các container khác của môi trường developer.

## 12. So sánh hai image một cách có căn cứ

| Tiêu chí | Dockerfile | Buildpacks |
| --- | --- | --- |
| Cách cấu hình | Tường minh bằng instructions | Builder/buildpacks phát hiện và cấu hình |
| Base OS/runtime | Nhóm phát triển chọn trực tiếp | Builder metadata và run image quyết định |
| Java runtime | Chọn từ base image | Chọn qua buildpack/provider, ví dụ `BP_JVM_VERSION` |
| User | Khai báo `USER` | CNB image mặc định chạy non-root |
| Entrypoint | Khai báo `ENTRYPOINT`/`CMD` | Buildpack đóng góp process type/launcher |
| Layering | Dockerfile instruction và BuildKit | Buildpack layers theo component |
| Caching | Docker/BuildKit layer cache | CNB build/launch layer caches |
| Tùy chỉnh OS packages | Rất trực tiếp trong Dockerfile | Thường cần custom builder/run image hoặc buildpack |
| JVM memory/runtime config | Environment/command flags do nhóm tự quản lý | Có buildpack-provided runtime components và variables |
| Debugging | Dễ xem từng instruction/layer | Cần hiểu builder, lifecycle, buildpack logs/process |
| Bảo trì | Nhóm quản lý Dockerfile/base image | Nhóm quản lý builder/buildpack versions và policies |
| Reproducibility | Pin base image digest, tools và build inputs | Pin builder/run image digest, buildpack/JVM inputs |
| Portability | Docker-compatible tools | CNB-compatible platform/Pack và builder |

Không kết luận Buildpacks luôn tạo image nhỏ hơn hoặc nhanh hơn Dockerfile. Kết quả phụ thuộc builder, run image, layer strategy, app dependencies, cache state, compression và platform.

## 13. Khi nào nên chọn Dockerfile?

Dockerfile phù hợp khi:

- Ứng dụng cần package hệ điều hành, certificates hoặc native libraries cụ thể.
- Nhóm cần kiểm soát từng filesystem layer và entrypoint.
- Runtime có quy tắc hardening riêng, UID/GID hoặc filesystem layout đặc biệt.
- Cần tích hợp các công cụ/sidecar assets hoặc startup scripts đặc thù.
- Đội vận hành đã có Dockerfile templates, policies và scanner gates được chuẩn hóa.

Ví dụ cần thêm một CA certificate hoặc native package vào runtime image: Dockerfile có thể mô tả chính xác package và vị trí file. Nhưng phải kiểm soát nguồn package, version, checksum và update cadence.

Dockerfile không tự đảm bảo image an toàn. Một Dockerfile chạy root, dùng base image lỗi thời, copy secrets hoặc cài package không pin vẫn có thể tạo image rủi ro.

## 14. Khi nào nên chọn Buildpacks?

Buildpacks phù hợp khi:

- Ứng dụng theo cấu trúc chuẩn Maven/Gradle và runtime phổ biến.
- Muốn giảm số lượng Dockerfile tùy chỉnh phải bảo trì.
- Muốn builder tự phát hiện loại app và chọn buildpacks.
- Muốn tận dụng layer caching, JVM provisioning và process types có sẵn.
- Nhiều service dùng chung builder policy và runtime baseline.
- Tổ chức muốn chuẩn hóa builder/run images và buildpack versions.

Buildpacks đặc biệt hữu ích khi team phát triển ứng dụng tập trung vào source/POM, còn platform team quản lý builder và runtime stack.

Nếu cần tùy chỉnh sâu OS packages, certificates hoặc filesystem layout, có thể tạo custom builder/run image hoặc buildpack riêng. Việc đó làm tăng trách nhiệm duy trì builder và tương thích lifecycle.

## 15. Dockerfile multi-stage: build source bên trong Docker

Mục 8 sử dụng JAR build sẵn để so sánh cùng input bytes. Một cách Dockerfile thường gặp khác là build source ngay trong Docker bằng **multi-stage build**.

Ví dụ Dockerfile thay thế:

~~~dockerfile
FROM maven:3.9.11-eclipse-temurin-17 AS build

WORKDIR /workspace

COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

RUN chmod +x mvnw \
    && ./mvnw -B -ntp dependency:go-offline

COPY src/ src/

RUN ./mvnw -B -ntp clean verify

FROM eclipse-temurin:17-jre-jammy AS runtime

WORKDIR /app

COPY --from=build --chown=10001:10001 \
    /workspace/target/image-build-comparison-1.0.0.jar \
    /app/application.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Trong build stage:

- Maven/JDK và dependencies chỉ tồn tại trong stage build.
- Copy `pom.xml` và Wrapper trước để tận dụng cache dependency layer.
- Copy `src/` sau khi dependency layer đã được tạo.
- Chạy `clean verify` để build và test.

Trong runtime stage:

- Chỉ copy executable JAR.
- Dùng JRE 17.
- Chạy non-root user.
- Không đưa Maven, source tree và compiler vào final image.

Multi-stage build làm final image chỉ nhận những file được COPY từ các stage trước. Nó giảm thành phần build tools trong runtime image và giúp tách build/runtime environments.

**Lưu ý về so sánh:** multi-stage Dockerfile trên build lại JAR trong Docker. Nếu Buildpacks cũng build từ source, hai đường có thể tạo archive khác bytes do thời điểm, toolchain, environment hoặc build metadata. Để kiểm tra cùng binary một cách chặt chẽ, dùng phương pháp build JAR một lần ở mục 7 rồi dùng Dockerfile runtime-only và Pack CLI như mục 8–9.

## 16. Layer caching và tối ưu thời gian build

### 16.1. Dockerfile cache

Docker/BuildKit cache từng instruction dựa trên instruction và inputs liên quan. Cấu trúc:

~~~dockerfile
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN ./mvnw dependency:go-offline
COPY src/ src/
RUN ./mvnw -B -ntp clean verify
~~~

giúp thay đổi source code không làm mất cache của layer tải dependencies nếu POM/Wrapper không đổi.

Cache không thay thế dependency repository. Khi dependency version thay đổi, layer cần được tạo lại và Maven resolve dependencies theo POM/settings.

### 16.2. Buildpacks cache

CNB lifecycle có analyze/restore để tái sử dụng layers từ image/cache trước. Buildpacks chia các phần JVM, application và các component khác thành layers theo metadata và buildpack behavior.

Một lần build đầu tiên có thể cần pull builder, run image và tải JRE. Lần sau có thể nhanh hơn nhờ cache. Để benchmark công bằng:

1. Chạy một cold build cho cả hai phương pháp.
2. Chạy một warm build cho cả hai phương pháp.
3. Dùng cùng host, Docker daemon, architecture và network.
4. Ghi rõ cache có được giữ hay xóa.
5. Không so cold Docker build với warm Buildpacks build.

### 16.3. Build cache khác release artifact

Docker BuildKit cache và CNB layer cache phục vụ tăng tốc. Image tag/digest là đầu ra cần chuyển giao và phát hành.

Không dùng cache layer như danh tính của sản phẩm. Image cần được tag, scan, lưu registry digest và gắn với source revision/build record.

## 17. Java runtime, port và environment configuration

### 17.1. Khóa Java major version

Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy
~~~

Buildpacks:

~~~text
BP_JVM_VERSION=17
BP_JVM_TYPE=JRE
~~~

Hai cấu hình yêu cầu Java 17. Tuy nhiên chúng có thể dùng vendor và patch versions khác nhau. Kiểm tra `java -version` trong từng image nếu runtime patch/provider là một phần của policy.

### 17.2. Runtime environment variables

Ứng dụng Spring Boot nhận cấu hình qua environment variables. Ví dụ đổi port:

~~~bash
docker run --rm \
  --publish 18082:18082 \
  --env SERVER_PORT=18082 \
  local/image-build-comparison:dockerfile
~~~

Spring Boot relaxed binding ánh xạ `SERVER_PORT` thành `server.port`. Với Buildpacks image, truyền environment tương tự:

~~~bash
docker run --rm \
  --publish 18083:18083 \
  --env SERVER_PORT=18083 \
  local/image-build-comparison:buildpacks
~~~

`EXPOSE 8080` trong Dockerfile chỉ là metadata. Nếu đổi server port, cập nhật host/container port mapping phù hợp. Buildpacks không tự làm ứng dụng Spring Boot lắng nghe một port khác nếu application configuration không thay đổi.

### 17.3. JVM flags

Dockerfile image có thể nhận:

~~~bash
docker run --rm \
  --env JAVA_TOOL_OPTIONS="-XX:+ExitOnOutOfMemoryError" \
  local/image-build-comparison:dockerfile
~~~

Paketo cũng hỗ trợ `JAVA_TOOL_OPTIONS` và các biến runtime chuyên biệt như `BPL_JVM_HEAD_ROOM` hoặc `BPL_JVM_THREAD_COUNT` cho những runtime components tương ứng. Xem đúng phiên bản Java Buildpack và tránh copy các biến `BPL_` không được buildpack hiện tại hỗ trợ.

Không đưa secrets vào Dockerfile `ENV` hoặc build arguments có thể bị lưu trong image history/metadata. Cấp secrets qua runtime secret store hoặc orchestrator.

## 18. Bảo mật và supply chain

### 18.1. Non-root user

Dockerfile mẫu dùng:

~~~dockerfile
USER 10001:10001
~~~

Buildpacks images do Spring Boot plugin tạo được thiết kế để build/run non-root. Dù vậy, cần inspect image thực tế và test ứng dụng trong môi trường tương tự production.

Không cấp root chỉ để khắc phục một lỗi permission. Xác định chính xác file/path cần ghi, rồi cấp quyền tối thiểu hoặc mount writable volume.

### 18.2. Base image và builder image

Dockerfile cần kiểm soát:

- Base image vendor/tag/digest.
- JRE patch/security update.
- OS package inventory.
- CA certificates và native libraries.
- User, filesystem permissions và exposed ports.

Buildpacks cần kiểm soát:

- Builder image và digest.
- Buildpack IDs/versions.
- Build image và run image metadata.
- JVM provider/version và runtime components.
- Registry source, trust và update cadence.

Buildpacks giảm thao tác viết Dockerfile nhưng không loại bỏ trách nhiệm quản lý builder/run image.

### 18.3. SBOM và vulnerability scanning

Cả hai images cần được kiểm tra:

- Application dependencies.
- JRE và OS packages.
- Buildpack/runtime components.
- Native libraries và CA packages.
- License/notice obligations.
- Vulnerability findings và remediation policy.

Buildpacks có thể cung cấp SBOM metadata cho các thành phần do buildpacks quản lý. Dockerfile image có thể được scan bằng công cụ SBOM/image scanner của tổ chức. Không giả định Maven dependency tree đã mô tả toàn bộ packages trong OCI image.

Dùng scanner được tổ chức phê duyệt, lưu kết quả theo image digest và đánh giá findings theo policy. Một scan PASS chỉ áp dụng cho đúng image digest đã scan.

### 18.4. Registry digest và provenance

Các định danh sau có ý nghĩa khác nhau:

~~~text
Git commit SHA  : source revision
JAR SHA-256     : executable archive bytes
Image tag       : tên tham chiếu có thể được cập nhật
Image digest    : định danh nội dung OCI manifest/index
~~~

Sau khi push registry, lưu digest thực tế do registry trả về. `docker image inspect .Id` trên local image thường là image config ID, không nên nhầm với manifest/index digest được dùng để deploy đa nền tảng.

Gắn image digest với source commit, JAR SHA-256, builder/base image digests, CI run ID và SBOM. Nếu tag bị di chuyển, digest vẫn là định danh nội dung đã được publish.

## 19. Reproducibility và multi-platform

### 19.1. Vì sao hai lần build có thể tạo digest khác?

Ngay cả khi source code không đổi, image digest có thể thay đổi do:

- Base image/builder tag trỏ tới digest mới.
- JRE patch version hoặc OS packages được cập nhật.
- Buildpack/plugin version thay đổi.
- Archive timestamp hoặc image created date khác.
- Architecture khác nhau.
- Layer ordering/compression/image config khác.
- Environment variables hoặc build arguments khác.

Để tăng khả năng tái lập, pin versions/digests, giữ build inputs, kiểm soát network dependencies và lưu SBOM/provenance.

### 19.2. Multi-platform images

Một image có thể hỗ trợ `linux/amd64` và `linux/arm64`. Docker Buildx có thể build/publish nhiều platform; Buildpacks cần builder/run images hỗ trợ platform được chọn.

Spring Boot Maven Plugin có option `imagePlatform` trong các version hỗ trợ, còn Pack/buildpack platform phụ thuộc builder và CLI. Không giả định builder hỗ trợ mọi architecture.

Với multi-platform release, lưu manifest-list/index digest và kiểm tra platform-specific image đã được tạo. Chạy smoke test trên từng architecture quan trọng; không chỉ test image amd64 rồi kết luận arm64 giống hệt.

## 20. CI pipeline cho hai cách đóng gói

Một pipeline tổng quát:

~~~text
Checkout exact commit
        |
        v
Set up JDK 17 + Maven Wrapper
        |
        v
mvn clean verify
        |
        v
Build executable JAR once
        |
        v
Copy to dist/application.jar
        |
        v
Calculate JAR SHA-256
        |
        +----------------------------+
        |                            |
        v                            v
Dockerfile build                 Pack build
        |                            |
        v                            v
Docker image A                   CNB image B
        |                            |
        +-------------+--------------+
                      |
                      v
          Smoke-test same HTTP endpoint
                      |
                      v
            Scan both image digests
                      |
                      v
             Store SBOM + provenance
                      |
                      v
          Approve and publish exact images
~~~

### 20.1. GitHub Actions job mẫu

Đoạn workflow dưới minh họa phần build và tạo hai images trên một Linux runner đã có Docker daemon và Pack CLI:

~~~yaml
name: Compare Dockerfile and Buildpacks

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  image-build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build and verify the application
        run: ./mvnw -B -ntp clean verify

      - name: Prepare the common executable JAR
        shell: bash
        run: |
          set -eu
          mkdir -p dist
          cp target/image-build-comparison-1.0.0.jar dist/application.jar
          sha256sum dist/application.jar > dist/application.jar.sha256

      - name: Build Dockerfile image
        run: |
          docker build --file Dockerfile \
            --tag local/image-build-comparison:dockerfile .

      - name: Build Buildpacks image
        run: |
          pack build local/image-build-comparison:buildpacks \
            --path dist/application.jar \
            --builder paketobuildpacks/builder-noble-java-tiny:latest \
            --env BP_JVM_VERSION=17 \
            --env BP_JVM_TYPE=JRE

      - name: Verify image metadata
        run: |
          docker image inspect local/image-build-comparison:dockerfile
          docker image inspect local/image-build-comparison:buildpacks
~~~

Runner phải cài Pack CLI và có Docker daemon trước bước `pack build`. Trong production, pin action versions bằng commit SHA theo policy, pin builder/base image digest, scan images và chạy smoke tests cho cả hai tags.

### 20.2. Release gate

Chỉ publish khi:

- JAR đã vượt qua Maven verify và smoke test.
- Hai image được build từ cùng JAR SHA-256 theo bài lab.
- Cả hai container trả cùng response từ `GET /health`.
- Java major/runtime, user và exposed ports đúng policy.
- Image scans và SBOM được lưu theo digest.
- Builder/base image digests và source commit được ghi lại.
- Người có thẩm quyền đã phê duyệt đúng image digests.

Không build lại một image sau khi scan/approval rồi tái sử dụng kết quả scan cũ cho digest mới.

## 21. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `docker build` báo không tìm thấy `dist/application.jar` | Chưa copy JAR vào dist hoặc .dockerignore loại file | Kiểm tra file trước build và ignore rules |
| `pack build` không detect ứng dụng Java | Đường dẫn app sai, file không phải executable JAR hoặc manifest thiếu | Kiểm tra JAR bằng `jar tf` và manifest |
| Buildpacks không tìm thấy Docker daemon | Docker Engine chưa chạy hoặc context/permission sai | `docker info`, Docker context và quyền daemon |
| Builder image pull thất bại | Registry/network/credential hoặc tag sai | Kiểm tra builder reference, registry auth và network |
| Spring Boot Maven `build-image` chạy package nhưng không tạo image | Docker daemon hoặc builder phase thất bại | Đọc lifecycle logs và Docker daemon connection |
| Image build thành công nhưng container exit ngay | Entrypoint/process type hoặc app startup lỗi | `docker logs` và inspect command/user |
| Dockerfile image chạy nhưng Buildpacks image không chạy | JRE/runtime config/process type khác | Kiểm tra buildpack logs, `BP_JVM_VERSION`, image user và process |
| Buildpacks image chạy nhưng Dockerfile image permission denied | File ownership hoặc user không phù hợp | `COPY --chown`, writable path và UID/GID |
| Endpoint không trả lời | Port mapping sai hoặc app bind port khác | Kiểm tra `SERVER_PORT`, `EXPOSE` và `docker port` |
| Docker image có Java sai major | Base image tag/runtime không như mong đợi | Chạy `java -version` trong image và pin digest |
| Buildpacks image dùng JRE patch khác dự kiến | Buildpack/provider tải patch mới hơn | Kiểm tra SBOM/JVM metadata và pin builder/runtime inputs |
| Dockerfile image lớn hơn kỳ vọng | Base image/build tools hoặc file thừa bị copy | Multi-stage build, .dockerignore và runtime base |
| Buildpacks build lần hai không nhanh hơn | Cache không được giữ hoặc image/cache identity đổi | Kiểm tra CNB cache volumes, builder và image tag |
| Hai image digest khác nhau | Layer/config/base image/created metadata khác | Bình thường; so cùng input JAR và runtime contract |
| Local Docker build chạy nhưng CI không chạy | Runner thiếu Docker daemon/Pack hoặc permission | Chuẩn bị runner và daemon access |
| Image chạy local nhưng production lỗi | Environment, architecture, registry digest hoặc secrets khác | So image digest, platform, runtime env và logs |
| Maven plugin build-image chọn nhầm archive | Multi-module hoặc nhiều JAR trong target | Chọn module/classifier/source archive đúng |
| Multi-arch pull ra image khác local | Platform manifest chọn image theo architecture | Kiểm tra manifest/index và platform-specific tests |

### 21.1. Lệnh điều tra nhanh

~~~bash
docker version
docker info
pack version
docker image ls local/image-build-comparison
docker image inspect local/image-build-comparison:dockerfile
docker image inspect local/image-build-comparison:buildpacks
docker logs image-dockerfile
docker logs image-buildpacks
docker port image-dockerfile
docker port image-buildpacks
~~~

Kiểm tra file đầu vào:

~~~bash
sha256sum dist/application.jar
jar tf dist/application.jar
~~~

Nếu lỗi chỉ xảy ra trong một phương pháp, giữ lại builder logs/Docker build logs của đúng lần build và so runtime config trước khi đổi source code.

## 22. Checklist trước khi chọn và phát hành image

### Application artifact

- [ ] Cùng source commit và Maven coordinates.
- [ ] JDK/compiler release được pin theo runtime baseline.
- [ ] `mvn clean verify` thành công.
- [ ] Executable JAR có manifest/Boot loader/dependencies đúng.
- [ ] JAR SHA-256 được lưu trong build record.
- [ ] Cả hai phương pháp nhận đúng archive đầu vào trong bài so sánh.

### Dockerfile

- [ ] Base image/JRE version được kiểm soát.
- [ ] Final stage chỉ có runtime files cần thiết.
- [ ] User là non-root.
- [ ] `COPY` không đưa secrets hoặc file build thừa vào image.
- [ ] Entrypoint dùng exec form.
- [ ] Port mapping và runtime environment được kiểm tra.

### Buildpacks

- [ ] Builder image/digest được kiểm duyệt.
- [ ] Buildpacks và JVM provider/version phù hợp.
- [ ] `BP_JVM_VERSION` được đặt đúng major.
- [ ] Docker daemon và registry access hoạt động.
- [ ] Run image phù hợp với builder metadata.
- [ ] Image chạy bằng non-root user.
- [ ] Cache và SBOM được quản lý theo policy.

### Release

- [ ] Cả hai images vượt qua cùng HTTP smoke tests.
- [ ] Image scan và SBOM gắn với digest.
- [ ] Source commit, JAR SHA-256, builder/base image digests được lưu.
- [ ] Tag release và registry digest được ghi nhận.
- [ ] Không dùng cache tag mutable làm deployment identity.
- [ ] Deployment dùng digest đã phê duyệt.

## 23. Câu hỏi tự kiểm tra

**A. Dockerfile và Buildpacks có cùng tạo OCI image không?**

Có. Dockerfile dùng Docker build instructions; Buildpacks dùng builder/lifecycle để tạo image. Cả hai có thể tạo image tuân theo OCI.

**B. Vì sao bài thực hành build JAR một lần trước khi tạo hai images?**

Để cả hai cách nhận cùng bytes của executable JAR. Nếu mỗi phương pháp tự build source độc lập, archive có thể khác do toolchain, timestamps hoặc environment.

**C. Buildpacks có cần Docker daemon không?**

Trong bài lab dùng Pack CLI và Spring Boot Maven Plugin, cần Docker-compatible daemon để xây dựng image. Một số platform triển khai CNB khác có cách tích hợp daemon/registry riêng.

**D. `BP_JVM_VERSION=17` có pin chính xác JRE patch không?**

Không. Nó chọn Java major 17. JRE patch/provider cụ thể phụ thuộc buildpack version và dependency metadata; cần kiểm tra SBOM/runtime và pin builder inputs theo policy.

**E. Buildpacks có chạy root trong runtime không?**

CNB images do Spring Boot build-image tạo được thiết kế để chạy non-root. Vẫn nên inspect image và kiểm tra user thực tế.

**F. Hai images có cùng digest nếu dùng cùng JAR không?**

Không. Base image, JRE, layer boundaries, image config, metadata và compression có thể khác. Cần so input JAR hash và behavior thay vì đòi digest giống nhau.

**G. Khi nào nên dùng `build-image-no-fork`?**

Khi bind image build goal vào Maven lifecycle. Khi gọi trực tiếp trên command line, dùng `spring-boot:build-image`.

**H. Dockerfile multi-stage có còn hữu ích khi dùng Buildpacks không?**

Có, nếu dự án cần kiểm soát build/runtime stages, OS packages hoặc custom runtime. Buildpacks và Dockerfile là hai cách đóng gói có thể lựa chọn theo yêu cầu vận hành.

**I. `EXPOSE 8080` có làm container tự publish port không?**

Không. Nó là metadata trong image. Cần map port bằng `docker run -p hostPort:containerPort` hoặc cấu hình tương ứng trong orchestrator.

**J. Nếu scan image tag thành công, có thể deploy tag đó mãi mãi không?**

Không nên. Tag có thể trỏ tới digest mới. Lưu và deploy digest đã scan/phê duyệt, đồng thời scan lại khi image thay đổi.

## 24. Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 — Packaging OCI Images / Maven `build-image`: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Spring Boot 3.5 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Docker — Multi-stage builds: https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/
- Docker — Build best practices: https://docs.docker.com/build/building/best-practices/
- Cloud Native Buildpacks — What is a builder?: https://buildpacks.io/docs/for-app-developers/concepts/builder/
- Cloud Native Buildpacks — Lifecycle: https://buildpacks.io/docs/for-platform-operators/concepts/lifecycle/
- Paketo — Build Java applications with Paketo Buildpacks: https://paketo.io/docs/howto/java/
- Paketo — Java Buildpack reference: https://paketo.io/docs/reference/java-reference/
- Paketo — Configure Buildpacks: https://paketo.io/docs/howto/configuration/
- Paketo — Executable JAR Buildpack: https://github.com/paketo-buildpacks/executable-jar
- Pack CLI — Install and usage: https://buildpacks.io/docs/tools/pack/

**Ghi nhớ:** Dockerfile cho phép nhóm phát triển mô tả trực tiếp runtime image; Buildpacks dùng builder và lifecycle để phát hiện ứng dụng, chuẩn bị runtime và tạo layers. Hai cách đều có thể đóng gói cùng một Spring Boot application. Hãy build một JAR đã kiểm chứng, dùng cùng bytes làm đầu vào, chạy cùng smoke tests và lưu riêng image digest/SBOM/provenance của từng image. Chọn phương pháp dựa trên mức kiểm soát runtime, khả năng tùy chỉnh và năng lực vận hành mà sản phẩm cần.