# So sánh Buildpacks với Dockerfile theo khả năng tùy biến và yêu cầu vận hành

## 1. Hai cách đóng gói cùng một ứng dụng Java

Trong Spring Boot, bạn có thể tạo một container image mà **không cần viết Dockerfile** bằng Cloud Native Buildpacks (CNB), hoặc bạn có thể tự định nghĩa image bằng Dockerfile. Hai lựa chọn đều có thể tạo OCI-compatible images cho Docker và Kubernetes, nhưng khác nhau về **khả năng tùy biến, quyền kiểm soát hệ điều hành, quy trình cập nhật, chi phí bảo trì và hạ tầng CI/CD**.

**Bài toán:** một nhóm có nhiều Spring Boot REST services muốn chọn công nghệ đóng gói thống nhất. Các services thông thường không cần thư viện hệ điều hành đặc biệt, nhưng một vài ứng dụng cần công cụ native, certificates tùy biến và filesystem layout cụ thể. Nên dùng CNB cho tất cả, Dockerfile cho tất cả, hay kết hợp hai phương án?

Bài này giúp bạn:

1. Nắm cơ chế `buildpack`, `builder image`, `run image`, CNB lifecycle và Dockerfile stages.
2. So sánh hai cách theo **mức tùy biến** (Java runtime, OS packages, native libraries, process, entrypoint, filesystem, security) và **yêu cầu vận hành** (CI, caching, registry, patching, SBOM, rebase, proxy, multi-platform, incident response).
3. Tạo **cùng một Spring Boot 4.1.2/Java 17 service**; từ đó tạo image bằng Maven `spring-boot:build-image` và bằng Dockerfile multi-stage.
4. Chạy hai images trên hai host ports, xác nhận HTTP body bằng nhau, rồi so metadata/entrypoint/layers một cách đúng đắn.
5. Hiểu cách dùng `BP_JVM_VERSION` ở build time, các `BPL_*` và `JAVA_TOOL_OPTIONS` lúc runtime với Paketo.
6. Nhận diện rủi ro ở môi trường enterprise: custom builder, run-image compatibility, base-image updates, CVE, cache ephemeral runners, registry credentials, root/non-root và compliance.
7. Chọn công nghệ dựa trên điều kiện thực tế thay vì kết luận phiến diện rằng “Buildpacks luôn tốt hơn” hoặc “Dockerfile luôn linh hoạt hơn nên luôn tốt hơn”.

**Ngữ cảnh:** *Spring Boot Build Tooling Packaging → Cloud Native Buildpacks*. Mẫu dùng Java 17, Spring Boot Maven Plugin **4.1.2**, Maven và Docker. Người học cần Maven/JDK và quyền sử dụng Docker daemon hoặc một build service đã được tổ chức phê duyệt. Builder/runtime image tags trong tài liệu là ví dụ; production cần quản lý versions và digests.

## 2. Sơ đồ nguồn vào và sản phẩm đầu ra

~~~text
                         Java source + pom.xml
                                   |
                           Maven verify/package
                                   |
                        Spring Boot executable JAR
                                   |
             +---------------------+---------------------+
             |                                           |
     Cloud Native Buildpacks                          Dockerfile
             |                                           |
     builder image + buildpacks                 FROM / RUN / COPY / USER
     run image + CNB lifecycle                  multi-stage + BuildKit
             |                                           |
      OCI application image                         OCI application image
             |                                           |
             +---------------------+---------------------+
                                   |
                            Docker / Kubernetes
~~~

**Một executable JAR chưa phải container image.** Maven `package` tạo `target/*.jar`, còn Spring Boot `build-image` hoặc `docker build` tạo một OCI image có runtime OS, Java, ứng dụng và metadata. Build thành công cũng **chưa có nghĩa đã push** image lên registry, ký image hay triển khai.

### Buildpacks tạo image như thế nào?

CNB gồm những thành phần liên quan nhau:

| Thành phần | Vai trò |
| --- | --- |
| **Buildpack** | Chứa logic `detect`/`build` để nhận diện ứng dụng, cài runtime hoặc đóng góp launch layers |
| **Builder image** | Build environment có buildpacks, lifecycle, order và những công cụ cần thiết |
| **Run image** | Base runtime layers của final application image |
| **CNB lifecycle** | Điều phối detection, analysis, restore, build, export; cung cấp launcher/rebase mechanisms |
| **CNB launcher** | Khởi động process type mà buildpacks chọn theo metadata của image |

Mô tả đơn giản:

~~~text
detect -> analyze -> restore -> build -> export
                                   |
                       selected Java buildpacks
                        + JRE/runtime layer
                        + app/dependency layers
                        + launch process metadata
                                   |
                             OCI image
~~~

Builder image **khác** run image: builder chứa môi trường build; final image dựa trên run image và launch/app layers. Vì vậy không được suy luận rằng mọi tool trong builder đều xuất hiện trong final runtime image.

### Dockerfile tạo image như thế nào?

Dockerfile mô tả quá trình thông qua những instruction tường minh:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/demo.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Với multi-stage build, một stage dùng Maven/JDK để build, stage sau dùng JRE để chạy. Dockerfile kiểm soát file copy, quyền sở hữu, OS packages, shell commands, entrypoint và image configuration. Các instruction có thể được cache bởi Docker/BuildKit; **Dockerfile không đồng nghĩa chậm hoặc image lớn**.

## 3. Điểm mạnh và giới hạn về khả năng tùy biến

### 3.1. Java version và JVM vendor

**Buildpacks:** với Paketo Java Buildpack, có thể dùng `BP_JVM_VERSION=17` để yêu cầu Java major version. Builder/buildpacks quyết định JDK/JRE provider nào được hỗ trợ, cấu trúc runtime image và các launch hooks. Có thể chọn custom builder, alternate JVM buildpack hoặc run image tương thích khi cần thay vendor.

**Dockerfile:** chọn trực tiếp `FROM eclipse-temurin:17-jre` hoặc base image Java khác; có thể copy custom JRE tạo bởi `jlink` nếu được kiểm thử. Mức linh hoạt cao nhưng người viết Dockerfile chịu trách nhiệm chọn/duy trì base.

**Cùng một Java target bytecode không tự bảo đảm cùng JVM runtime.** Nên ghi rõ runtime major, vendor, patch level, architecture và OS base để so sánh công bằng.

### 3.2. OS packages, native libraries và certificates

**Buildpacks** có thể hỗ trợ native dependencies, custom CA, certificates và tools thông qua buildpacks, extensions, custom builder/run images hoặc bindings của nền tảng. Nhưng nếu một đội cần chạy tùy ý `apt-get install` bên trong image cho một binary đặc thù, cấu hình thường **phức tạp hơn một Dockerfile** nếu chưa có custom CNB platform.

**Dockerfile** có thể dùng `RUN apt-get` hoặc `apk` theo base distro để cài packages. Điều này dễ quan sát qua code review, nhưng đổi lại phải quản lý package sources, versions, CVEs, cleanup và license. **Không đưa secrets vào image layers qua `COPY`/`RUN`**.

### 3.3. Filesystem và process startup

- CNB image có launch contract/process metadata và filesystem conventions từ buildpacks. Không nên giả định ENTRYPOINT là `["java","-jar",...]` hay JAR nằm ở `/app/app.jar`.
- Dockerfile có thể chỉ định `WORKDIR`, `USER`, `RUN`, `COPY --chown`, `ENTRYPOINT` và `CMD`. Hữu ích khi cần startup script, writable directory, timezone data, native binary hoặc một policy process đặc biệt.
- Không nên thay CNB launcher bằng raw `java` khi chưa hiểu launch hooks; có thể làm mất chức năng của buildpack runtime.
- Đừng dùng shell-form ENTRYPOINT vô ý làm shell giữ PID 1 và không forward SIGTERM. Cả hai images cần kiểm tra shutdown behavior thực tế.

### 3.4. Build cache và layers

CNB quản lý build/launch layers theo input, metadata và caching lifecycle. Docker/BuildKit quản lý cache theo instruction graph, image stages và cache mounts. Một Dockerfile có thể tận dụng Spring Boot layered JAR và COPY thành nhiều image layers; ngược lại Buildpacks không bảo đảm cache tốt nếu runner không giữ cache volumes.

**Tốc độ build và image size phải đo**, không thể suy từ “có Dockerfile” hay “có Buildpacks”. Rebuild một Java source class khác với cập nhật base OS, thay lockfiles hoặc đổi runtime JDK.

### 3.5. Rebase khi OS có lỗ hổng

CNB hỗ trợ **rebase**: thay run-image layers của application image bằng các lớp nền mới khi metadata/stack/platform **tương thích**, không cần rebuild application layers. Đây có thể là lợi thế vận hành khi OS runtime có CVE.

Nhưng rebase **không tự nâng cấp Maven dependencies, JVM layers do buildpacks đóng góp, business code hoặc native libraries ở app layers**; không được coi là thay thế mọi lần rebuild. Cần công cụ rebaser, registry access, compatibility và regression tests. Dockerfile thường đổi `FROM` digest rồi rebuild/test; quy trình dễ hiểu nhưng có thể tốn thời gian hơn trong một số tình huống.

## 4. Ma trận so sánh tổng hợp

| Yêu cầu | Cloud Native Buildpacks | Dockerfile |
| --- | --- | --- |
| Spring Boot service chuẩn, ít ngoại lệ | Ít cấu hình per-service | Cần Dockerfile hoặc shared template |
| Java runtime | Builder/buildpacks/`BP_JVM_VERSION` | Base image hoặc JRE do mình copy |
| Native/OS packages | Custom buildpack/run image/extension | `RUN` install trong stage phù hợp |
| ENTRYPOINT/launch hooks | Dựa vào CNB launcher và buildpack metadata | Kiểm soát trực tiếp `ENTRYPOINT`/`CMD` |
| User và permissions | Phụ thuộc builder/run policy; phải kiểm tra | `USER`/`COPY --chown` tường minh |
| Cache | CNB layers, buildCache/launchCache | Dockerfile order, BuildKit cache mounts |
| OS security update | Có thể rebase khi compatible | Đổi base image và rebuild |
| SBOM | CNB ecosystem có metadata/SBOM tùy buildpack | Dùng Docker/OCI tooling hoặc scanners |
| Source provenance | Builder/buildpack versions và lifecycle | Dockerfile, base digest và build logs |
| Image size | Phụ thuộc run image/JVM/layers | Phụ thuộc base/multi-stage/packages |
| CI | Spring Boot `build-image` cần Docker daemon | Docker/BuildKit hoặc build service |
| Proxy/offline | Mirror builder, run image, JRE, buildpack artifacts | Mirror base image, Maven/OS repositories |
| JVM options runtime | `BPL_*`/`JAVA_TOOL_OPTIONS` theo buildpack | Java env options/ENTRYPOINT config |
| Multi-platform | Builder/run/buildpacks hỗ trợ platform | Buildx/`--platform`, builder/emulation |
| Platform governance | Central approved builder/run image hữu ích | Central Dockerfile templates/base-image policy |
| Chi phí bảo trì ngoại lệ | Có thể phải phát triển custom buildpack | Dễ thêm vài instruction nhưng phải cập nhật lâu dài |
| Security | Không tự động an toàn chỉ vì dùng CNB | Không tự động an toàn chỉ vì có Dockerfile |

**Đừng đánh đồng** “customizable” với “free of maintenance”: linh hoạt hơn đồng nghĩa phải sở hữu nhiều quyết định về runtime OS, package manager, security và update process.

## 5. Ví dụ Spring Boot 4.1.2 dùng cho cả hai phương pháp

Ta tạo một service HTTP có kết quả dễ kiểm chứng. Dùng **chính cùng source** để so sánh Buildpacks image và Dockerfile image.

### 5.1. Cấu trúc thư mục

~~~text
catalog-svc/
├── pom.xml
├── Dockerfile
├── .dockerignore
├── src/
│   ├── main/
│   │   ├── java/dev/example/catalog/
│   │   │   ├── CatalogApplication.java
│   │   │   └── CatalogMessage.java
│   │   └── resources/application.properties
│   └── test/
│       └── java/dev/example/catalog/CatalogMessageTest.java
└── target/
~~~

### 5.2. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>catalog-svc</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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
                        <name>catalog-svc:cnb</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích:**

- Starter parent quản lý dependency versions và goal `repackage` cho executable JAR; Java target là 17.
- `spring-boot-starter-webmvc` cấp dependencies cho Spring MVC và embedded servlet server.
- Image name là `catalog-svc:cnb` để không ghi đè image `catalog-svc:docker` của Dockerfile.
- `BP_JVM_VERSION=17` là input **builder environment** của Paketo Java buildpack; không tự thay `java.version` trong Maven compiler.
- Không pin builder trong POM demo để dùng builder mặc định được Spring Boot 4.1.2 chọn. **Khi phát hành thực tế phải kiểm soát builder/run image tags và digests**; `latest` không phải chính sách reproducibility.

### 5.3. `CatalogMessage.java`

Tệp `src/main/java/dev/example/catalog/CatalogMessage.java`:

~~~java
package dev.example.catalog;

public final class CatalogMessage {
    private CatalogMessage() {
    }

    public static String value() {
        return "IMAGE_OK";
    }
}
~~~

### 5.4. `CatalogApplication.java`

Tệp `src/main/java/dev/example/catalog/CatalogApplication.java`:

~~~java
package dev.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @GetMapping("/healthz")
    public String healthz() {
        return CatalogMessage.value();
    }
}
~~~

Endpoint `/healthz` của demo trả một body cố định. **Đây không phải một production readiness check đầy đủ**: ứng dụng thật nên kiểm tra dependency health hoặc dùng Actuator với security policy phù hợp.

### 5.5. `application.properties`

Tệp `src/main/resources/application.properties`:

~~~properties
spring.application.name=catalog-svc
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.banner-mode=off
~~~

Giữ port **8080** bên trong cả hai images. Đây là điểm cần thống nhất trước khi so sánh runtime behavior.

### 5.6. `CatalogMessageTest.java`

Tệp `src/test/java/dev/example/catalog/CatalogMessageTest.java`:

~~~java
package dev.example.catalog;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CatalogMessageTest {
    @Test
    void returnsStableOutput() {
        assertEquals("IMAGE_OK", CatalogMessage.value());
    }
}
~~~

JUnit test xác minh logic, **chưa** xác minh image có startup đúng. Ta sẽ bổ sung smoke test HTTP sau khi tạo images.

## 6. Cloud Native Buildpacks: build bằng Spring Boot Maven Plugin

### 6.1. Prerequisites

Đối với **lệnh `mvn spring-boot:build-image`** trong bài:

- Java 17 và Maven tương thích/Wrapper của project.
- Docker daemon hoặc Docker API endpoint mà Maven Plugin kết nối được.
- Quyền Docker socket/context đúng, policy network và image pull phù hợp.
- Truy cập builder/run images, registry và JRE artifacts, hoặc mirror/proxy đã cấu hình.
- Disk/cache volume và memory của builder đủ để chạy CNB lifecycle.
- CI có policy cho phép tạo container/volumes tạm và thu dọn.

Kiểm tra:

~~~bash
java -version
mvn -version
docker info
~~~

Có Docker CLI **không có nghĩa Docker daemon hoạt động**. Nếu `docker info` không kết nối được, xử lý context/permissions/daemon theo chính sách hệ thống, không tự mở quyền Docker socket toàn cục.

### 6.2. Tạo Buildpacks image

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp spring-boot:build-image
~~~

Goal `spring-boot:build-image` là lệnh thích hợp khi gọi trực tiếp; nó có thể fork lifecycle để bảo đảm packaging xảy ra. Khi muốn bind image build vào một Maven `<execution>` trong lifecycle, Spring Boot cung cấp goal `build-image-no-fork`; không gắn `build-image` rồi bất ngờ chạy vòng build lặp.

Image mong đợi theo cấu hình:

~~~text
catalog-svc:cnb
~~~

**Tạo local image khác push registry.** Lệnh trên tạo image trong Docker daemon mà plugin kết nối, trừ khi có cấu hình publish khác. Không coi image có tag là bằng chứng đã có immutable digest ở registry.

### 6.3. Inspect image

~~~bash
docker image inspect catalog-svc:cnb
docker history catalog-svc:cnb
~~~

Để xem entrypoint/user:

~~~bash
docker image inspect catalog-svc:cnb \
  --format 'USER={{.Config.User}} ENTRYPOINT={{json .Config.Entrypoint}}'
~~~

CNB image có thể có **CNB launcher** làm entrypoint chứ không phải `java -jar /app/app.jar`. Đó là khác biệt kiến trúc hợp lệ. Phải kiểm tra process metadata và chạy app thực, không lấy entrypoint Dockerfile làm tiêu chí sai cho Buildpacks image.

### 6.4. Tùy biến builder/run image

Spring Boot Maven Plugin cho phép cấu hình image builder/run image:

~~~xml
<!-- Fragment thuộc <configuration> của spring-boot-maven-plugin -->
<image>
    <name>catalog-svc:cnb</name>
    <builder>registry.example.invalid/platform/java-builder:approved</builder>
    <runImage>registry.example.invalid/platform/java-run:approved</runImage>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
    </env>
</image>
~~~

**Đây chỉ là fragment minh họa**: tên ở domain `example.invalid` không được định nghĩa là real registry image; không copy chạy nguyên văn. Builder/run image thật cần tương thích với nhau, lifecycle, architecture, stack/run-image requirements và policy tổ chức.

Các tùy chọn khác của Maven Plugin gồm `imagePlatform`, `pullPolicy`, `createdDate`, `buildpacks`, `buildCache`, `launchCache`, `buildWorkspace`, Docker connection và publish/registry configuration. Không phải builder nào cũng hỗ trợ mọi tên biến Paketo, nên cần xem documentation đúng builder.

**Về pinning:** theo tài liệu Spring Boot Maven Plugin 4.1.2, builder mặc định có thể dùng một image `latest` từ Paketo và `pullPolicy` mặc định là `ALWAYS`. Với release production, nên quản lý builder/run image digests hoặc version đã phê duyệt cùng update schedule. Không phải pin xong là an toàn mãi: phải cập nhật và kiểm tra CVE thường xuyên.

## 7. Dockerfile multi-stage: build cùng ứng dụng

### 7.1. `Dockerfile` hoàn chỉnh

~~~dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml ./pom.xml
COPY src ./src
RUN mvn -B -ntp clean verify

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build --chown=10001:10001 \
    /workspace/target/catalog-svc-1.0.0.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Đọc từng instruction:**

1. `FROM maven:3.9-eclipse-temurin-17 AS build` có Maven và JDK 17 để compile/test/package, không ở final image.
2. `COPY pom.xml` và `COPY src` đưa source vào build stage. Khi có nhiều Maven modules, phải COPY đủ parent POM/modules và build extensions.
3. `RUN mvn -B -ntp clean verify` chạy unit tests và tạo executable JAR. Nếu test fail, Docker build fail; không skip tests vô tình.
4. `FROM eclipse-temurin:17-jre` tạo runtime stage chỉ cần JRE; tag là ví dụ, production pin digest.
5. `COPY --from=build` lấy đúng executable Boot JAR, không mang source code/Maven repo hay compiler sang runtime.
6. `USER 10001:10001` tránh chạy root. Kiểm tra app cần ghi file ở đâu, ví dụ `/tmp`, log directory, mounted volumes.
7. `EXPOSE 8080` chỉ là metadata; publish host port khi `docker run -p`.
8. Exec form `ENTRYPOINT ["java", "-jar", "/app/app.jar"]` truyền signals trực tiếp hơn so với shell-entrypoint parent; vẫn cần app graceful shutdown.

Dockerfile này được thiết kế để học và kiểm chứng. Với production, tách cache resolution, sử dụng BuildKit cache mounts, update base images, security scans và digest pinning theo CI policy.

### 7.2. `.dockerignore`

~~~text
.git
.idea
.vscode
target
build
*.log
.DS_Store
~~~

Vì multi-stage Dockerfile **tự build JAR từ source**, không loại `pom.xml` hoặc `src` khỏi context. `target` nên được bỏ khỏi context để không copy artifacts cũ ngoài ý muốn. Nếu dùng Dockerfile khác chỉ COPY pre-built JAR, quy tắc `.dockerignore` phải thay tương ứng để không loại artifact cần thiết.

### 7.3. Build image

~~~bash
docker build -t catalog-svc:docker .
~~~

Image tạo ra ở local Docker daemon. Bạn có thể xác minh:

~~~bash
docker image inspect catalog-svc:docker
docker history catalog-svc:docker
~~~

Không phải mọi Docker host đều hỗ trợ cùng phiên bản BuildKit/Buildx; với Dockerfile này, multi-stage build là chức năng đã được dùng rộng rãi, nhưng các kỹ thuật cache nâng cao cần builder phù hợp.

### 7.4. Tùy biến OS packages

Dockerfile có lợi thế khi bạn thực sự cần cài gói hệ điều hành:

~~~dockerfile
# Fragment: chèn sau FROM runtime, trước USER không-root.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
~~~

**Đây không phải phần bắt buộc của ví dụ**, vì base image có thể đã có CA certificates. Dùng đúng package manager của distro; image tối giản/distroless có thể **không có shell/package manager**, lúc đó phải tạo/chuẩn bị filesystem qua build stage khác.

Cấu hình pin package versions, repositories và vulnerability updates là trách nhiệm pipeline Dockerfile. Buildpacks cũng có thể cung cấp custom OS libraries bằng custom run image/buildpack/extension, nhưng đòi năng lực quản lý builder/run image tương ứng.

## 8. Chạy song song và kiểm chứng cùng một API

Chạy hai image ở hai host ports khác nhau:

~~~bash
docker run -d --name catalog-cnb \
  -p 18080:8080 catalog-svc:cnb

docker run -d --name catalog-docker \
  -p 18081:8080 catalog-svc:docker
~~~

Sau khi cả hai ứng dụng đã ready (CI nên chờ bằng readiness loop/timeout):

~~~bash
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18081/healthz
~~~

**HTTP response body chính xác của mỗi lệnh:**

~~~text
IMAGE_OK
~~~

Đây là **HTTP response body**, không phải stdout của `docker run`. Buildpacks image có launcher/logs khác Dockerfile image mà vẫn đáp ứng cùng hợp đồng chức năng. Không so startup logs như những chuỗi luôn giống nhau.

Kiểm tra thêm:

~~~bash
docker ps
docker logs catalog-cnb
docker logs catalog-docker
docker image inspect catalog-svc:cnb
docker image inspect catalog-svc:docker
~~~

Dọn hai container vừa tạo:

~~~bash
docker stop catalog-cnb catalog-docker
docker rm catalog-cnb catalog-docker
~~~

**Không suy ra hai image phải có cùng SHA-256/digest.** Base/run image, JRE provider, labels, entrypoint, timestamps và filesystem layers khác nhau; endpoint giống nhau chứng minh một phần **functional equivalence**, không chứng minh byte-for-byte identity.

## 9. Build-time và runtime options: `BP_*` khác `BPL_*`

Paketo Java Buildpack cung cấp những cơ chế tùy biến theo giai đoạn:

| Biến hoặc nhóm | Giai đoạn | Ý nghĩa |
| --- | --- | --- |
| `BP_JVM_VERSION` | Build time | Chọn major Java runtime được đóng vào image |
| `BPL_JVM_THREAD_COUNT` | Runtime | Tham số cho memory calculator của buildpack JVM |
| `BPL_JVM_HEAD_ROOM` | Runtime | Headroom cho JVM sizing theo buildpack |
| `JAVA_TOOL_OPTIONS` | Runtime Java | Bổ sung JVM flags theo cơ chế Java/toolchain |
| `SPRING_PROFILES_ACTIVE` | Runtime Spring Boot | Chọn cấu hình application profile |
| `JDK_JAVA_OPTIONS` | Java 17 launcher | Truyền Java launcher/VM options, hữu ích trong Dockerfile image |
| `BP_*` khác | Build time | Chỉ có ý nghĩa nếu buildpack đang dùng nhận tên đó |
| `BPL_*` khác | Runtime | Chỉ có ý nghĩa nếu runtime helpers/buildpacks hỗ trợ |

### Buildpacks runtime ví dụ

~~~bash
docker run --rm -p 18082:8080 \
  --memory=512m \
  -e BPL_JVM_THREAD_COUNT=100 \
  -e JAVA_TOOL_OPTIONS='-Ddemo.flag=from-cnb' \
  catalog-svc:cnb
~~~

**Không dùng `BP_JVM_VERSION` ở runtime để mong đổi JRE đã được đóng vào image.** Nó là build-time input của Paketo; JRE version ở runtime cần chọn tại build và được xác minh bằng SBOM/runtime diagnostics.

Buildpack JVM memory calculator có thể dùng cgroup limits, thread count, class count, headroom... để định JVM flags; không được khẳng định heap do CNB tạo bằng với image Dockerfile. Các `BPL_*` không phải tiêu chuẩn bắt buộc của mọi CNB builder.

### Dockerfile runtime ví dụ

~~~bash
docker run --rm -p 18083:8080 \
  --memory=512m \
  -e JDK_JAVA_OPTIONS='-Xms64m -Xmx256m -Ddemo.flag=from-docker' \
  catalog-svc:docker
~~~

Java 17 launcher hiểu `JDK_JAVA_OPTIONS` mà không cần Docker shell expansion. `JAVA_OPTS` **không** phải biến môi trường Java launcher tự đọc theo tiêu chuẩn; chỉ có tác dụng nếu image sử dụng script/launcher hỗ trợ nó.

**Quan trọng:** `-Xmx` đặt **sau `-jar`** trong Docker `CMD` không phải JVM option mà thành application argument. Khi tùy biến Dockerfile, đặt JVM flags trước `-jar` hoặc dùng env vars Java hỗ trợ. CNB launcher cần tuân theo quy định riêng của builder, không thay bằng raw `java -jar` khi chưa hiểu launch hooks.

## 10. Image size, cache và tốc độ: cách đánh giá không thiên lệch

### 10.1. Size

Không khẳng định CNB luôn tạo image nhỏ hơn Dockerfile hoặc ngược lại. Size phụ thuộc:

- Run image/base OS (distro, glibc, CA/SSL packages).
- JDK hay JRE; Java vendor và runtime modules.
- Library dependencies và các files/resources được đóng gói.
- Native/OS packages tùy chỉnh và layer ordering.
- Compression của registry, architecture và image manifest.

Kiểm tra:

~~~bash
docker image ls catalog-svc
docker history --no-trunc catalog-svc:cnb
docker history --no-trunc catalog-svc:docker
~~~

**Đừng so chỉ bằng con số `SIZE` local:** shared layers, compressed registry size và nhiều architectures có thể làm các thước đo khác nhau. Chọn metric gắn với chi phí/speed của tổ chức: transfer bytes, cold pull time, image footprint và storage.

### 10.2. Cache

**CNB:** lifecycle/cache restore/export có thể reuse JRE/app/dependency layers. Spring Boot Maven Plugin có `buildCache` và `launchCache`; mặc định cache thường là Docker named volumes dựa trên image name. CI ephemeral có thể mất volumes, còn thay image names/tags thường xuyên có thể làm caching kém.

**Dockerfile:** BuildKit dùng instruction caching. Ví dụ `COPY src` rồi `RUN mvn ...` có thể invalidated Maven stage khi source đổi. Dùng cache mounts cho `~/.m2`, remote caches và tách build artifact khỏi image stage để tối ưu. Không đồng nghĩa Dockerfile luôn phải download toàn bộ dependencies.

**Đo trên hai workload:** (a) no-change rebuild và (b) sửa một class Java. Dùng **cùng CI runner resources, network, registry, JDK target và source**; ghi thời gian build, cache hits và digest. Không dùng cached artifact rồi kết luận đã chứng minh rebuild reproducibility.

### 10.3. Reproducibility

Một builder image tag `latest` và Dockerfile `FROM ...:latest` đều có thể trỏ đến digests khác sau vài ngày. Khi cần xây lại cùng release:

- Pin source commit và dependency versions/locks.
- Pin/kiểm toán Maven plugin, CNB builder/run images hoặc Docker base image digests.
- Kiểm soát generated metadata như `build.time`, archive timestamp và toolchain.
- Lưu SBOM/provenance cùng digest image.
- Chạy hai independent builds khi cần QA reproducibility thực sự.

**Reproducible artifact không tự an toàn:** hai image byte-identical vẫn có thể cùng mang lỗ hổng; cần scanning và patching.

## 11. Bảo mật, SBOM và cập nhật CVE

### 11.1. Rủi ro chung

Cả hai phương án đều có thể gặp:

1. CVE ở OS, JRE, native libraries và Java dependencies.
2. Image tag thay đổi mà không pin digest.
3. Registry credentials/build secrets lộ trong layers, build logs hoặc environment.
4. CI chạy quá nhiều quyền (ví dụ Docker socket không kiểm soát).
5. Application process chạy root, thiếu network restrictions hoặc writable filesystem dư thừa.
6. Thiếu provenance, signatures, SBOM hoặc license checks.
7. Image được publish nhưng không có quy trình nâng cấp base runtime sau khi có CVE.

**Không có công cụ nào tự giải quyết cả bảy vấn đề chỉ vì nó tạo image được.**

### 11.2. Buildpacks giúp tập trung governance

Platform team có thể quản lý một bộ approved builder/run images, JVM vendor và buildpack versions. Tất cả Spring Boot services chuẩn được đóng gói theo cùng quy tắc, giảm các Dockerfile sao chép không được cập nhật.

CNB ecosystem hỗ trợ SBOM/BOM từ buildpacks và rebase run image khi phù hợp. Tuy nhiên **SBOM completeness phụ thuộc builder/buildpacks/tooling**. Trước khi tuyên bố compliance, phải kiểm tra artifact cụ thể, scanner và chứng từ provenance.

### 11.3. Dockerfile giúp review từng instruction

Dockerfile hiển thị `FROM`, `RUN`, `COPY`, `USER` và entrypoint rõ ràng; platform team có thể áp policy-as-code/lint. Nhưng nếu `RUN curl ... | sh` mà không pin/check checksum hoặc apt packages tự đổi, chính sự linh hoạt đó có thể làm supply chain khó kiểm soát.

### 11.4. Gợi ý provenance

Một release nên ghi lại thông tin ở mức:

~~~text
source.commit       = <Git SHA>
image.reference     = registry.example.com/team/catalog-svc:1.0.0
image.digest        = sha256:<digest thực tế sau build/push>
java.runtime        = <vendor/version>
os.base.digest      = <run image hoặc base image>
builder.toolchain   = <CNB lifecycle/buildpacks hoặc Docker/BuildKit>
sbom.reference      = <SBOM artifact>
scan.result         = <policy result>
ci.run              = <execution record>
~~~

Đây là **mẫu trường**, không phải SHA hoặc attestation đã được tạo trong bài. Ghi **digest thật**, không dùng tag làm identity duy nhất. CI run ID/creation timestamp có thể lưu ngoài image để tránh nhúng metadata biến động vào ứng dụng.

## 12. Hạ tầng CI: Docker daemon, proxy, registry và cache

### 12.1. Với Spring Boot Maven `build-image`

- Plugin giao tiếp với Docker daemon/API. Docker CLI có sẵn không bảo đảm daemon/socket khả dụng.
- Builder/run images phải pull được; private registry cần credentials phù hợp.
- Builder phải truy cập nguồn tải JRE/buildpack dependencies hoặc mirror. Proxy/CA khác biệt giữa **host**, **Docker daemon** và **builder container** có thể gây lỗi bất ngờ.
- `pullPolicy` theo tài liệu Spring Boot Maven Plugin 4.1.2 mặc định `ALWAYS`; cần lưu ý khi builder tag chuyển digest.
- Cache volumes/workspace có thể tiêu thụ disk lớn, nhất là nhiều image names.
- `imagePlatform` cho phép chọn target platform được builder hỗ trợ; không tự tạo multiarch manifest list.
- Có thể cấu hình Docker host/TLS, registry publish và build-time env/bindings theo Maven Plugin, nhưng không nên hardcode secrets trong POM.

**Phân biệt:** `spring-boot:build-image` cần Docker daemon; **Cloud Native Buildpacks nói chung không bắt buộc mỗi developer có daemon local**. CNB lifecycle có thể dùng qua `pack`, kpack hoặc platform/build service đã được tổ chức triển khai. Yêu cầu hạ tầng phụ thuộc tích hợp cụ thể.

### 12.2. Với Dockerfile/BuildKit

- Cần Docker/BuildKit builder hoặc dịch vụ remote builder phù hợp.
- Multi-stage build Maven cần Maven repositories/proxies/auth trong build stage.
- Có thể dùng remote cache và Buildx multi-platform, nhưng phải chọn builder/architecture phù hợp.
- Nếu Dockerfile COPY một prebuilt JAR, CI phải bảo đảm JAR đó được tạo từ commit đúng và tests đã chạy; không sử dụng stale artifact.
- Build secrets nên đưa qua mechanism được build service hỗ trợ, không sao chép credential vào runtime image.
- Rootless/restricted CI có thể không cho phép thông thường Docker daemon; cả hai phương pháp cần giải pháp builder được phê duyệt.

### 12.3. Multi-platform và native dependencies

Bytecode Java có thể portable giữa amd64/arm64, nhưng JRE, OS packages, JNI/native image dependencies phụ thuộc architecture. CNB yêu cầu builder/run images/buildpacks hỗ trợ platform đích. Docker Buildx hỗ trợ nhiều platforms khi builder, emulation và base images cho phép.

**Không kết luận image `linux/amd64` có thể triển khai trực tiếp trên `linux/arm64`**. Nếu deployment multiarch, tạo và publish đúng image variants/manifest index, rồi test trên architecture thực tế.

## 13. Bảng lựa chọn theo yêu cầu vận hành

| Bối cảnh | Ưu tiên ban đầu | Điều kiện phải kiểm tra |
| --- | --- | --- |
| Nhiều REST services thuần Java, ít native dependencies | Buildpacks | Approved builder/run image, CI và security policy |
| Ứng dụng cần font/native imaging library trong OS | Dockerfile hoặc custom CNB | Package manager, run image compatibility, CVE policy |
| Muốn cập nhật runtime OS hàng loạt | Buildpacks có lợi thế khi rebase phù hợp | Rebase tooling, registry permissions, regression QA |
| Phải chỉ định entrypoint/USER/filesystem chi tiết | Dockerfile | Process signals, permissions, container probes |
| Muốn giảm boilerplate per repo | Buildpacks | Platform team duy trì builder/builder upgrades |
| Có Dockerfile templates/BuildKit mạnh sẵn | Dockerfile có thể phù hợp | Cache, base digest, scanning vẫn chuẩn hóa |
| CI ephemeral không giữ Docker volumes | Cần benchmark | CNB cache và BuildKit remote caches |
| Compliance bắt buộc SBOM/attestation | Cả hai có thể | Kiểm chứng tools/metadata bằng digest thật |
| Cần amd64 và arm64 | Cả hai có thể | Builder/run platform hoặc Buildx manifest |
| CI cấm daemon socket | Phụ thuộc build service | CNB alternative platform hoặc remote BuildKit |
| Cần image size cực nhỏ | Không đoán | Đo cùng Java, OS features và security requirements |
| OS package custom vừa có một vài services | Tùy platform maturity | Chi phí custom buildpack so với Dockerfile |
| Không có đội bảo trì Dockerfiles | Buildpacks thường dễ bắt đầu | Builder supply chain vẫn cần owner |
| Runtime memory được platform tính tự động | Paketo Buildpacks có thể có lợi | BPL knobs, actual cgroup/memory behavior |

**Đề xuất thực tế:** nếu đa số workload chuẩn Java/Spring Boot và platform team đã quản lý CNB builder tốt, chọn Buildpacks làm **default path**; cho phép Dockerfile như **exception path** khi OS packages, entrypoint hoặc compliance yêu cầu. Cả hai phải vượt qua cùng bộ QA/security gates.

## 14. Kiểm thử vận hành ngoài chức năng HTTP

### 14.1. Identity và metadata

~~~bash
docker image inspect catalog-svc:cnb \
  --format 'ID={{.Id}} USER={{.Config.User}}'
docker image inspect catalog-svc:docker \
  --format 'ID={{.Id}} USER={{.Config.User}}'
~~~

Xem architecture, base image labels, user, entrypoint, env và layers. **Không buộc user/entrypoint của hai image giống nhau**; chỉ so với policy của từng image. Image Buildpacks có thể dùng CNB launcher và image Dockerfile có Java exec ENTRYPOINT.

### 14.2. Memory và JVM runtime

~~~bash
docker run --rm --memory=512m \
  -p 18084:8080 catalog-svc:cnb
~~~

Đây là một **container memory limit**, không tương đương JVM `-Xmx512m`. Java còn dùng native memory, metaspace, thread stacks, direct buffers và code cache. Đo heap/GC/native memory trên workload đại diện, đừng kết luận từ startup success.

### 14.3. Shutdown

~~~bash
docker run -d --name catalog-stop \
  -p 18085:8080 catalog-svc:docker
docker stop --time 30 catalog-stop
docker logs catalog-stop
docker rm catalog-stop
~~~

Docker gửi stop signal theo runtime configuration và sau grace period có thể buộc dừng process. Spring Boot có graceful shutdown nhưng phải thử với requests/background jobs thực, không coi `server.shutdown=graceful` là lời đảm bảo mọi request hoàn tất.

### 14.4. Security hardening

Kiểm tra: non-root, read-only filesystem khi thích hợp, writable mounts, Linux capabilities, network policy, secret injection, image signing, vulnerability scanning, SBOM, provenance, update SLAs và rollback. **Đừng cho Docker daemon socket hoặc build credentials vào runtime container**.

## 15. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `spring-boot:build-image` không kết nối Docker | Daemon/socket/context/TLS chưa hợp lệ | `docker info`, plugin Docker connection |
| CNB không detect app | JAR/source format hoặc builder buildpacks không phù hợp | Maven `package`, lifecycle logs, chosen builder |
| CNB builder thay đổi giữa các lần build | Upstream `latest`/`pullPolicy` kéo image mới | Pin approved versions/digests, release policy |
| CNB cần native OS library không có | Run image thiếu binary/lib | Custom run image/buildpack hoặc Dockerfile |
| `BP_JVM_VERSION` không hiệu lực | Builder không dùng Paketo component hoặc input sai | Xem builder/buildpacks, logs, runtime Java |
| Java class version exception | Compiler target và runtime JRE không tương thích | Đồng bộ Java 17 target/run image |
| Docker `COPY` báo không thấy JAR | Multi-stage path sai hoặc build chưa tạo JAR | Kiểm tra `target` trong build stage |
| Docker image final chứa Maven/JDK nhiều | Không dùng multi-stage đúng | Tách build/runtime stages |
| Docker build chậm mỗi lần sửa source | Cache invalidated khi `COPY src` | Tối ưu instructions, Maven/BuildKit cache |
| CNB build chậm ở CI nhưng nhanh local | Cache volumes không persistent | Cache policy/volumes, benchmark |
| Image CNB không chạy khi override entrypoint | Bỏ qua CNB launcher/hook | Giữ process default hoặc hiểu launch metadata |
| `BPL_*` không có tác dụng | Builder không hỗ trợ knob cụ thể | Kiểm tra Paketo docs/runtime buildpack |
| App OOM dù heap tưởng nhỏ | JVM native memory và container limits | Đo actual heap/native/cgroup |
| Docker runtime app không nhận SIGTERM | Shell form entrypoint giữ PID 1 | Exec ENTRYPOINT và kiểm tra stop |
| CNB rebase thất bại | Run image/metadata/platform không tương thích | Kiểm tra rebaser support và stack policy |
| Hai images có digest khác | Base/JRE/launcher/layer metadata khác | Bình thường; so chức năng và compliance |
| Dockerfile image scan fail | Base/OS packages hoặc dependencies có CVE | Cập nhật digests/packages, re-scan/retest |
| CI không push được registry | Credentials/namespace/permissions | Xác minh push step riêng |
| Image tag trỏ tới build khác | Tag mutable hoặc race giữa pipelines | Ghi digest thật và deploy by digest |
| App trong container không mở port | `server.port` và `docker run -p` không khớp | Test port trong container/host mapping |

**Thứ tự debug:** source và JDK → JAR packaging → CNB builder/buildpacks hoặc Dockerfile stage → OCI metadata → container runtime → registry/provenance. Không sửa Spring business code khi lỗi nằm ở builder/run image.

## 16. Quality gates trước khi release

**A. Source/JAR**

- [ ] Git commit xác định, Java version và Maven plugins được quản lý.
- [ ] Unit tests của Spring Boot được phát hiện/chạy thành công.
- [ ] Executable JAR build đúng source/commit.
- [ ] Dependency versions và SBOM provenance nhất quán.

**B. Container image**

- [ ] CNB image dùng builder/run image đã được phê duyệt.
- [ ] Dockerfile image dùng approved base image digests và multi-stage đúng.
- [ ] Image architecture, user, entrypoint, env và layers được inspect.
- [ ] Images đã được scan và đáp ứng policy về OS/JVM/dependency vulnerabilities.
- [ ] Image digest thật được ghi lại khi publish; không chỉ dùng mutable tags.

**C. Runtime**

- [ ] Cả hai images được thử với host ports riêng.
- [ ] HTTP `GET /healthz` của hai image trả **200 và body chính xác `IMAGE_OK`**.
- [ ] JVM memory/GC/thread/native memory được đo theo container cgroup.
- [ ] Stop/graceful shutdown và logs được kiểm chứng.
- [ ] Không có secrets hoặc Docker socket trong runtime image.
- [ ] Non-root, writable directories, security context đáp ứng yêu cầu.

**D. Operations**

- [ ] Có owner rõ cho builder/run images hoặc Dockerfile/base images.
- [ ] Cache strategy phù hợp với runner thực tế; không đánh giá chỉ trên laptop.
- [ ] Proxy/CA/registry/credentials đã thử ở CI và production.
- [ ] Có lịch patch CVEs và rollout/rollback theo image digest.
- [ ] SBOM/provenance/signing policy được áp trên cả hai phương án.
- [ ] Nếu cần rebase, xác minh kỹ thuật và chạy regression QA.
- [ ] Nếu cần multiarch, kiểm thử các target architectures và manifest index.

**Một image có HTTP 200 chưa đủ kết luận production-ready.** Nó chứng minh chức năng demo; performance, security, patching và observability vẫn cần kiểm tra riêng.

## 17. Bài tập tình huống có đáp án

**1. Service Spring Boot thuần REST không có OS dependencies đặc biệt, team có approved CNB builder. Nên thử phương án nào trước?**

Buildpacks là điểm khởi đầu hợp lý vì ít Dockerfile boilerplate và dễ dùng policy builder/run image chung. Sau đó xác minh CI cache, Java runtime, SBOM và security posture.

**2. Service cần gói font hệ điều hành và một binary native tự build. CNB có bị loại tuyệt đối không?**

Không; custom buildpack/run image/extension có thể đáp ứng. Nhưng nếu platform chưa có năng lực đó, Dockerfile thường cho cách cài/copy binary tường minh hơn. Cân nhắc chi phí ownership dài hạn.

**3. `BP_JVM_VERSION=17` có đổi `-Xmx` khi app đang chạy không?**

Không. Với Paketo, đó là build-time JVM version selection. Runtime sizing dùng các knobs `BPL_*` hoặc JVM options theo buildpack.

**4. `mvn spring-boot:build-image` có tự push image lên registry không?**

Không phải mặc định của workflow mẫu. Build tạo image qua Docker daemon; publish là một bước/cấu hình riêng, phải xác nhận registry digest.

**5. Vì sao CNB và Dockerfile images có hashes khác nhau nhưng trả cùng `IMAGE_OK`?**

Vì base OS, JRE vendor/patch, launcher, labels, file structure và layers khác nhau. Functional equivalence khác byte-identical OCI artifacts.

**6. CNB rebase thay tất cả Java dependencies theo `pom.xml` được không?**

Không. Rebase nhằm thay run-image layers khi tương thích, không thay app artifacts và không tự nâng cấp dependencies/JRE layers thuộc app build.

**7. Có thể dùng Dockerfile đa stage để tránh Maven/JDK trong final image không?**

Có. Dùng Maven/JDK stage để build JAR rồi copy chỉ JAR vào JRE runtime stage. Đây là cách tránh shipping build tools.

**8. CI cấm Docker daemon trên runner. Có phải CNB vô dụng không?**

Không. Spring Boot Maven `build-image` cần kết nối Docker daemon; CNB ecosystem có các build platforms khác. Dockerfile cũng có remote BuildKit/build services. Chọn giải pháp được tổ chức cho phép.

**9. Image Buildpacks có ENTRYPOINT khác `java -jar` có phải lỗi không?**

Không. CNB launcher và launch process metadata là một phần của cơ chế Buildpacks. Kiểm thử startup/HTTP và inspect metadata theo policy.

**10. Vì sao không nên chọn dựa hoàn toàn vào image size?**

Vì size phụ thuộc JRE, OS libraries, architecture, compression, shared layers và security functionality. Cần đo cùng feature set và các chỉ số vận hành khác.

**11. Buildpacks tự động giúp tránh cần người bảo trì CVE không?**

Không. Builder/run image, buildpacks và dependencies cần owner, upgrade schedule, scanning và rollback, tương tự base images/Dockerfile pipeline.

**12. Có nên dùng kết hợp hai cách trong một tổ chức?**

Có. Dùng Buildpacks làm common path cho Java services tiêu chuẩn; dùng Dockerfile hoặc custom builder cho workload đặc thù. Cả hai phải vượt cùng quality/security gates.

## 18. Checklist quyết định thiết kế

- [ ] Đã xác định yêu cầu custom OS packages/native dependencies.
- [ ] Đã xác định mức kiểm soát filesystem/ENTRYPOINT/process cần thiết.
- [ ] Đã xác định Java runtime vendor/version/patch policy.
- [ ] Đã kiểm tra approved builder/run images hoặc Docker base digests.
- [ ] Đã phân biệt build-time `BP_*` và runtime `BPL_*`.
- [ ] Đã đo cache trên CI thực, không dựa vào suy đoán.
- [ ] Đã kiểm chứng proxy, certificates và network download trong build.
- [ ] Đã xác minh registry auth, image publish và digest.
- [ ] Đã tính chi phí vá CVE, SBOM, license/provenance scans.
- [ ] Đã kiểm tra non-root/security context và graceful shutdown.
- [ ] Đã kiểm tra resource limits, heap/native memory và JVM startup.
- [ ] Đã kiểm chứng host/OCI architecture compatibility.
- [ ] Đã có rollback/rebuild/rebase strategy nếu base runtime thay đổi.
- [ ] Đã chạy smoke test chức năng với image thực tế.
- [ ] Đã chỉ định owner của builder/run images hoặc Dockerfile templates.
- [ ] Không dùng mutable `latest` làm duy nhất identity của release.
- [ ] Có lý do cụ thể để chọn Buildpacks, Dockerfile hoặc kết hợp.

**Kết luận:** **Buildpacks** giúp đóng gói Spring Boot theo conventions và giảm phần cấu hình lặp lại, đặc biệt hữu ích khi platform team duy trì builder/run images chung. **Dockerfile** phù hợp khi cần quyền kiểm soát tường minh từng bước, cài OS packages đặc thù và tùy biến entrypoint/filesystem. Không có lựa chọn thắng tuyệt đối: so sánh theo yêu cầu tùy biến, khả năng CI/vận hành, cache, security, upgrade và kết quả kiểm chứng trên cùng ứng dụng.

## 19. Tài liệu chính thức

1. [Spring Boot Maven Plugin 4.1.2 — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
2. [Spring Boot Gradle Plugin — OCI Image Packaging](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-images.html)
3. [Cloud Native Buildpacks — Documentation](https://buildpacks.io/docs/)
4. [Cloud Native Buildpacks — Platform Specification / Rebase](https://github.com/buildpacks/spec/blob/main/platform.md)
5. [Cloud Native Buildpacks — Lifecycle](https://github.com/buildpacks/lifecycle)
6. [Paketo — Java Buildpack and JVM Configuration](https://paketo.io/docs/buildpacks/language-family-buildpacks/java/)
7. [Docker — Dockerfile Reference](https://docs.docker.com/reference/dockerfile/)
8. [Docker — Build Best Practices](https://docs.docker.com/build/building/best-practices/)
9. [Docker — Multi-platform Builds](https://docs.docker.com/build/building/multi-platform/)
10. [Spring Boot — Dockerfiles for Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
11. [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)
12. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
