# Ngăn thông tin xác thực, khóa riêng và cấu hình nhạy cảm lọt vào archive hoặc image Spring Boot

## 1. Mục tiêu và ranh giới bảo mật

Một ứng dụng Spring Boot có thể được đóng gói thành executable JAR/WAR hoặc OCI container image. Trong quá trình đó, dữ liệu đi qua nhiều nơi: Git checkout, resource processing, Maven/Gradle build, archive, Docker build context, buildpack builder, cache, image layers, registry và runtime container. **Một secret xuất hiện ở bất kỳ bước nào cũng có thể bị lưu lại ngoài ý muốn.**

Những dữ liệu cần bảo vệ gồm:

- Password database, API token, OAuth client secret, session/signing key.
- SSH private key, TLS private key, PKCS12/JKS keystore và passphrase.
- Registry credentials, artifact repository credentials, cloud access keys, CI/CD tokens.
- File cấu hình production có chứa secret, connection string, private endpoint hoặc thông tin vận hành hạn chế.
- Credential dùng để ký artifact/image, khóa mã hóa, master key và recovery code.

**Đề bài không chỉ là tránh hard-code password trong Java.** Cần bảo vệ toàn bộ chuỗi:

~~~text
Source / Git / CI secrets
       |
       v
Maven / Gradle / resource processing
       |
       v
JAR / WAR / generated files
       |
       v
Docker build context / BuildKit / CNB builder
       |
       v
Build cache / image layers / metadata / registry
       |
       v
Runtime container / logs / diagnostics / backups
~~~

Bài học dùng **Java 17 và Spring Boot 3.3.13**, với Maven hoặc Gradle, Docker BuildKit và Cloud Native Buildpacks. Đây là bộ phiên bản minh họa; khi áp dụng, hãy kiểm tra compatibility và chính sách bảo mật của phiên bản toolchain đang dùng. Những lệnh trong bài là hướng dẫn để người học chạy trong môi trường được phép, không phải kết quả build/scan đã thực hiện sẵn.

Sau khi hoàn thành, bạn có thể:

1. Phân biệt build-time credentials, runtime secrets và configuration không nhạy cảm.
2. Đưa secrets ra khỏi source, resource filtering, JAR/WAR, Docker build context và image.
3. Cấp quyền đọc artifact repository/private Git và quyền publish image mà không lưu credential trong POM/Gradle script/Dockerfile.
4. Sử dụng Docker BuildKit secret mount đúng cách và hiểu vì sao ARG/ENV không phù hợp để truyền build secrets.
5. Cấu hình Spring Boot đọc secret từ file được mount bằng configtree.
6. Kiểm tra archive, image, Git history, build logs và cache để tìm dấu hiệu rò rỉ.
7. Xử lý sự cố đã lộ credential bằng revoke/rotate, rebuild, thay image và rà soát các bản sao cũ.

## 2. Phân biệt secret, private key và cấu hình thông thường

Không phải mọi giá trị cấu hình đều là secret. Việc phân loại giúp quyết định giá trị nào có thể đóng trong archive.

| Loại dữ liệu | Ví dụ | Có thể nằm trong JAR/image không? | Nơi cấp phù hợp |
| --- | --- | --- | --- |
| Cấu hình công khai/không nhạy cảm | Tên service, port, feature flag mặc định, URL public | Thường có thể, nếu không chứa thông tin nội bộ bị hạn chế. | application.properties, environment hoặc config file. |
| Cấu hình môi trường | Tên database, host nội bộ, region, timeout | Tùy phân loại nội bộ; nên externalize để cùng artifact chạy được ở nhiều môi trường. | Runtime config, ConfigMap, config service. |
| Credential | Password, API token, client secret | **Không.** | Secret manager, CI secret store, runtime secret mount. |
| Private key | SSH key, TLS private key, signing key, encryption key | **Không.** | HSM/KMS, Vault, secret manager hoặc secure runtime mount. |
| Public certificate/key | TLS certificate công khai, public verification key | Có thể, tùy chính sách và nhu cầu. | Trust store/CA bundle hoặc cấu hình public. |
| Build credential | Maven repository password, Git deploy key, registry token | Không được đóng vào sản phẩm. | Build runner secret store, short-lived token, BuildKit secret/SSH mount. |
| Test fixture | Token giả, password giả dành riêng cho test | Có thể trong test source/resources nếu chắc chắn là dữ liệu giả và không dùng được ở hệ thống thật. | Test fixture riêng, không tái sử dụng production secret. |

**Private key và certificate không giống nhau:** certificate/public key thường có thể chia sẻ để xác minh danh tính; private key cho phép ký, giải mã hoặc giả mạo danh tính và phải được bảo vệ nghiêm ngặt. Một file .p12/.jks có thể chứa cả certificate lẫn private key; hãy coi toàn bộ keystore và passphrase là dữ liệu nhạy cảm.

### 2.1. Build-time secret và runtime secret

**Build-time secret** chỉ cần để tạo sản phẩm, ví dụ credential tải dependency từ Maven repository riêng hoặc SSH key clone private Git repository. Nó chỉ nên hiện diện trong đúng bước build cần dùng.

**Runtime secret** được ứng dụng sử dụng sau khi container đã chạy, ví dụ database password hoặc API token. Không cần có mặt trong bước compile/package hoặc trong OCI image; runtime platform cung cấp khi deploy/start container.

| Secret | Khi nào cần? | Ví dụ xử lý |
| --- | --- | --- |
| Maven repository token | Khi Maven resolve dependency | settings.xml ngoài repository, CI secret store hoặc BuildKit secret mount. |
| Private Git SSH key | Khi clone source/private submodule trong build | SSH agent/BuildKit SSH mount. |
| Docker registry token | Khi pull builder/run image hoặc publish image | Docker credential helper hoặc Spring Boot plugin registry credentials lấy từ CI secret store. |
| Database password | Khi app mở kết nối runtime | Secret file mount và Spring Boot configtree. |
| TLS private key | Khi app terminate TLS/mTLS | Keystore/PEM mount lúc runtime; không copy vào image. |
| Artifact signing key | Khi ký JAR/image/release | HSM/KMS/remote signing service; không lưu private key trong workspace/image. |

**Không cấp một token quyền deploy chỉ để tải dependency.** Tách credential theo tác vụ, thời hạn ngắn, quyền tối thiểu và có thể thu hồi. Nếu nền tảng CI hỗ trợ workload identity/OIDC để nhận token ngắn hạn từ cloud/secret manager, ưu tiên cơ chế đó thay cho access key dài hạn.

## 3. Những con đường thường làm secret lọt vào sản phẩm

### 3.1. Source code và Git

Các ví dụ nguy hiểm:

~~~java
// KHÔNG LÀM: giá trị được biên dịch vào class file.
private static final String API_TOKEN = "prod-token-value";
~~~

~~~yaml
# KHÔNG LÀM: application-prod.yml trong repository có password thật.
spring:
  datasource:
    username: orders
    password: prod-database-password
~~~

~~~properties
# KHÔNG LÀM: secret trong resource của src/main/resources.
partner.api.token=prod-token-value
server.ssl.key-store-password=real-keystore-password
~~~

Dù sau đó xóa dòng hoặc xóa file khỏi commit mới nhất, secret vẫn có thể còn trong:

- Git commit/tree cũ, branch, tag, fork, pull request hoặc Git bundle.
- IDE local history, patch, backup, artifact CI, cache và log.
- Docker build context, image layer hoặc image registry.
- Maven/Gradle generated resources và JAR/WAR đã publish.

**.gitignore chỉ ngăn file chưa được track được thêm vào Git theo quy tắc ignore.** Nó không tự xóa file đã commit hoặc lịch sử cũ. Khi phát hiện credential thật trong Git, phải coi credential đã bị lộ và rotate/revoke; chỉ xóa file không thu hồi quyền truy cập.

### 3.2. Maven/Gradle resource processing

Maven Resource Plugin có thể thay placeholder bằng giá trị lấy từ project/system properties, filter files hoặc command line. Nếu một secret được đưa vào filter và resource đó được copy vào target/classes, secret có thể nằm trong JAR.

Gradle cũng có thể tạo resource qua processResources, expand, custom task hoặc generated source. Một task ghi token vào file output có thể làm token đi vào build/resources/main và archive.

**Không đưa secret vào filter file, resource expansion, generated source hoặc task output.** Chỉ filter allowlist những biến không nhạy cảm như application version/build number. Tách riêng resource được phép filter khỏi resource nhạy cảm và giữ secret file ngoài source tree.

### 3.3. Dockerfile và build context

Những cách thường làm lộ:

~~~dockerfile
# KHÔNG LÀM: giá trị tồn tại trong image configuration.
ENV DATABASE_PASSWORD=real-password

# KHÔNG LÀM: build arg có thể xuất hiện trong image history/provenance.
ARG REPOSITORY_TOKEN
RUN curl -H "Authorization: Bearer $REPOSITORY_TOKEN" https://repo.example.invalid/file

# KHÔNG LÀM: secret bị lưu trong filesystem layer.
COPY settings.xml /root/.m2/settings.xml
COPY secrets/ /app/secrets/
~~~

ENV được lưu trong image config và truyền vào container. ARG không được lưu như một environment variable runtime, nhưng Docker cảnh báo build arguments không phù hợp để truyền credential: chúng có thể xuất hiện trong docker history và provenance attestations. RUN echo secret > file hoặc COPY secret vào image tạo dữ liệu trong layer.

**Xóa file ở layer sau không xóa bytes trong layer trước.** Docker image layers bất biến; một lệnh RUN rm /app/secret.txt ở layer mới không làm secret biến mất khỏi layer cũ.

### 3.4. Cloud Native Buildpacks (CNB)

Spring Boot Maven Plugin spring-boot:build-image và Gradle bootBuildImage truyền application/build configuration vào builder để build image.

- environment/env trong plugin là biến được truyền **cho builder/buildpacks**; nó không đồng nghĩa với secret runtime được bảo vệ.
- Buildpack có thể đọc biến đó, ghi nó vào generated file, log, layer hoặc cache nếu logic buildpack làm vậy.
- Một số biến như Paketo BPE_* được thiết kế để lưu cấu hình vào image và áp dụng khi app khởi chạy; không dùng chúng cho password/token/private key.
- bindings là bind mount vào builder container. Mount read-only và đặt ngoài source/build context có thể hữu ích khi buildpack hỗ trợ service binding tương ứng, nhưng **bind mount không tự bảo đảm nội dung không bị buildpack copy vào layer/cache**.

Chỉ cung cấp build-time credential cho buildpack đã được kiểm tra, đúng bước cần dùng, với quyền tối thiểu. Kiểm tra cả builder logs, build workspace/cache và image output.

## 4. Nguyên tắc thiết kế để secret không đi vào archive/image

1. **Không đặt secret trong source, POM, Gradle script, Dockerfile, application resource hoặc file filter được commit.**
2. Tách build-time secret và runtime secret; không cấp runtime secret cho build process.
3. Dùng CI secret manager hoặc secret vault; lấy token ngắn hạn, chỉ cấp cho đúng job/step.
4. Với secret cần đọc trong build, dùng cơ chế tạm thời như Docker BuildKit secret/SSH mount hoặc cơ chế binding được buildpack hỗ trợ.
5. Với runtime, mount secret file hoặc dùng secret manager/runtime identity; ứng dụng đọc từ external config.
6. Không echo, log, serialize, in exception hoặc đưa secret vào build scan/diagnostic report.
7. Không đưa secret vào archive, OCI layer, image label, build metadata, SBOM annotation, provenance hoặc build cache.
8. Không chia sẻ build cache/workspace có chứa secret giữa những runner/tenant không tin cậy.
9. Scan source, Git history, archive và image trước khi publish.
10. Nếu lộ secret, **revoke/rotate trước**, sau đó xử lý các bản sao, rebuild và redeploy.

**Mục tiêu là giảm thời gian secret tồn tại trong build và thu hẹp số thành phần có quyền đọc nó.** Environment variable tiện dùng nhưng không tự động an toàn: process khác có đủ quyền trên host/container có thể đọc environment, và một số công cụ chẩn đoán có thể hiển thị chúng. Với dữ liệu nhạy cảm cao, file mount read-only hoặc secret manager API thường dễ kiểm soát hơn.

## 5. Spring Boot externalized configuration: đọc secret lúc runtime

Spring Boot cho phép lấy cấu hình từ application properties/YAML, environment variables, system properties, command line và các nguồn config data khác. Với secret, hãy để artifact chứa **tên property hoặc đường dẫn external**, còn giá trị thật được cấp ở runtime.

### 5.1. Ví dụ config tree cho secret files

Giả sử container được platform mount thư mục:

~~~text
/run/secrets/
├── partner.api.token
├── spring.datasource.username
├── spring.datasource.password
└── server.ssl.key-store-password
~~~

Tên file trở thành tên property; nội dung file là value. Trong src/main/resources/application.properties, chỉ khai báo:

~~~properties
spring.config.import=configtree:/run/secrets/

partner.api.base-url=https://api.partner.example
spring.datasource.url=jdbc:postgresql://db.internal:5432/orders
~~~

spring.config.import=configtree:/run/secrets/ yêu cầu Spring Boot đọc config tree. Các file spring.datasource.username và spring.datasource.password cung cấp properties tương ứng. **Không có password nào được ghi vào resource trong JAR.**

Đối với Docker Swarm secrets, Spring Boot có thể đọc secret files được mount dưới /run/secrets/ bằng configtree:. Kubernetes có thể mount Secret volume hoặc dùng CSI secret provider vào một đường dẫn tương tự.

**Lưu ý về optional:** optional:configtree:/run/secrets/ cho phép ứng dụng tiếp tục nếu đường dẫn không tồn tại. Chỉ dùng khi secret thực sự tùy chọn (ví dụ môi trường dev). Nếu production bắt buộc có credential, dùng import không có optional: để app fail fast khi thiếu secret, tránh khởi động với cấu hình sai hoặc mặc định không an toàn.

### 5.2. Bind properties trong Java mà không in secret

src/main/java/com/example/security/PartnerApiProperties.java:

~~~java
package com.example.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    private String baseUrl;
    private String token;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }
}
~~~

src/main/java/com/example/security/SecretSafeApplication.java:

~~~java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class SecretSafeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecretSafeApplication.class, args);
    }
}
~~~

PartnerApiProperties nhận partner.api.token từ config tree lúc runtime. Class này **không override toString() để in token**. Nếu dùng Lombok @Data, record hoặc log toàn bộ object, toString() có thể đưa token vào log; hãy loại secret khỏi toString() và log fields.

Khi gọi API, chỉ đặt token vào HTTP Authorization header trong client cần dùng. Không ghi header, full request object hoặc exception chứa header ra log. Không trả secret qua REST response hoặc Actuator endpoint.

### 5.3. Test chỉ dùng credential giả

Trong unit/integration test, dùng value giả như test-only-token, không sao chép credential thật từ staging/production. Nếu cần test config tree, tạo file tạm với dữ liệu giả trong thư mục test riêng, giới hạn quyền file và xóa sau test.

Không commit src/test/resources/application-prod.yml chứa credential thật. Không dùng chung API token thật giữa test và production vì test reports, CI artifacts và failure logs có thể được lưu lâu.

### 5.4. Environment variable và file mount

Có thể truyền config không nhạy cảm bằng environment variables, ví dụ:

~~~bash
SPRING_PROFILES_ACTIVE=prod
SERVER_PORT=8080
~~~

Nếu buộc phải dùng env variable cho credential, hãy cấp từ secret store ở runtime, giới hạn quyền xem process/container metadata và không dùng lệnh in toàn bộ environment.

Với secret có độ nhạy cao, ưu tiên mount file read-only rồi dùng configtree:. Không đưa secret vào application.properties bằng placeholder được expand ở **build time**; placeholder runtime có thể an toàn nếu nguồn value thực sự là external config, nhưng phải xác minh resource cuối cùng không chứa giá trị đã được thay thế.

## 6. Maven: giữ repository credentials ngoài POM và archive

### 6.1. Không lưu repository password trong pom.xml

Maven phân biệt:

- pom.xml: khai báo project, dependencies, repositories, plugins và build behavior.
- settings.xml: cấu hình theo máy/người dùng/CI như server authentication, mirror và proxy.

Với repository riêng, khai báo server ID phù hợp trong user/CI settings. File ~/.m2/settings.xml được cấp tạm trong build runner chứa một server entry có ID khớp repository ID trong POM, cùng username/password được secret manager inject lúc job chạy. **Không lưu giá trị thật trong POM hoặc file settings được commit.**

Trong pom.xml, repository dùng cùng ID:

~~~xml
<repositories>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
</repositories>
~~~

repo.example.invalid chỉ là domain minh họa. Thay bằng repository được tổ chức phê duyệt. Maven settings hỗ trợ cấu hình server authentication tách khỏi project POM.

**Không commit** ~/.m2/settings.xml, settings-security.xml, private key hoặc file settings tạm vào project. Giới hạn quyền đọc file, dùng workspace/agent riêng, xóa file tạm khi job kết thúc và tránh in help:effective-settings, help:effective-pom hoặc debug logs chứa credential.

### 6.2. Maven 3 password encryption không phải secret vault

Maven 3 có thể mã hóa/obfuscate password trong settings.xml, nhưng tài liệu Maven nói cơ chế này ở mức obfuscation, không chống được attacker quyết tâm có quyền đọc cả encrypted values và master password. Nó hữu ích để tránh lộ password qua screenshot/log đơn giản, **không thay thế secrets manager, quyền file hoặc CI secret store**.

Maven 4 có cơ chế encryption/dispatcher mới hơn, nhưng master key/source vẫn cần được bảo vệ. Dù dùng phiên bản nào, đừng commit credential hoặc master key vào source repository.

### 6.3. Resource filtering: allowlist giá trị được phép

Nếu Maven cần filter version/build metadata, tách thư mục:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/resources-filtered</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
</build>
~~~

src/main/resources-filtered chỉ chứa dữ liệu không nhạy cảm như version hoặc build number. **Không** thêm password/token/private key vào filter file hoặc properties truyền qua -D để Maven thay vào resource. Tránh bật filtering toàn bộ resource tree khi không cần.

Maven Resources Plugin còn cảnh báo không filter binary resources như ảnh/PDF vì có thể làm hỏng file. Hãy giữ resource binary và filtered text ở những thư mục riêng.

## 7. Gradle: cung cấp repository credentials qua typed credentials API

Không viết:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/maven')
        credentials {
            username = 'real-user'
            password = 'real-password'
        }
    }
}
~~~

Dùng tên repository và PasswordCredentials:

~~~groovy
repositories {
    maven {
        name = 'internal'
        url = uri('https://repo.example.invalid/maven')
        credentials(PasswordCredentials)
    }
}
~~~

Gradle sẽ tìm project properties theo tên repository: internalUsername và internalPassword. Trên CI, cấp chúng qua secret-backed environment variables:

~~~bash
ORG_GRADLE_PROJECT_internalUsername
ORG_GRADLE_PROJECT_internalPassword
~~~

Gradle hỗ trợ biến ORG_GRADLE_PROJECT_ để cung cấp project properties cho unattended builds. Có thể dùng GRADLE_USER_HOME/gradle.properties trên máy developer với quyền file chặt, nhưng **không commit** file project gradle.properties chứa credential.

Typed credentials API giúp Gradle quản lý credential theo repository identity và redacts giá trị khỏi một số build scan/error output. Dù vậy, vẫn phải bảo vệ runner, logs, Gradle user home và configuration/build cache; không println properties hoặc bật --debug rồi lưu output công khai.

### 7.1. Gradle properties không phải file để commit secret

Một project gradle.properties có thể chứa các flags không nhạy cảm, nhưng nếu nó chứa internalPassword, đừng commit. Dùng ORG_GRADLE_PROJECT_internalPassword từ CI secret store hoặc file trong Gradle user home được bảo vệ. Không đưa secret qua -P, -D hay command line vì shell history, process listing và CI command logs có thể lưu tham số.

### 7.2. Configuration cache và build cache

Configuration cache có thể lưu trạng thái cấu hình build để tái sử dụng; Gradle có cơ chế mã hóa cache entry, nhưng quyền đọc cache directory và encryption key vẫn cần giới hạn. Không copy GRADLE_USER_HOME từ runner có secrets sang workspace/artifact công khai.

Gradle build cache lưu **task outputs**. Nếu một task vô tình ghi token vào output file, output đó có thể được lưu trong local/remote cache. Task dùng secret phải đảm bảo output không chứa credential; tránh cache task sinh file cấu hình đã render với secret thật. Với task đặc biệt cần secret và tạo output nhạy cảm, xem xét tắt caching hoặc thiết kế lại để output không chứa secret.

## 8. Docker BuildKit: truyền build secret chỉ trong đúng lệnh cần dùng

### 8.1. Vì sao ARG và ENV không phù hợp?

| Cách | Có thể dùng cho | Vì sao không dùng cho secret? |
| --- | --- | --- |
| ARG | Build option không nhạy cảm như version, architecture. | Có thể xuất hiện trong docker history và provenance; không nên truyền password/token. |
| ENV | Runtime default không nhạy cảm, ví dụ SERVER_PORT. | Được lưu trong image config và tồn tại trong container. |
| COPY settings.xml | File build input công khai. | File copy vào layer và có thể còn trong image/cache. |
| RUN --mount=type=secret | Credential chỉ cần trong một RUN step của BuildKit. | Secret mount không tự ghi vào image; nhưng lệnh bên trong vẫn có thể copy/echo secret ra file/log nếu viết sai. |
| RUN --mount=type=ssh | SSH agent/socket để clone private Git. | Chỉ cung cấp socket trong bước cần dùng; không copy private key vào context. |

### 8.2. Ví dụ Dockerfile Maven multi-stage với BuildKit secret

Dockerfile sau minh họa build Spring Boot JAR trong builder stage. Maven settings.xml chỉ được mount trong các lệnh Maven cần truy cập private repository:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY pom.xml .
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml,required=true mvn -B -s /root/.m2/settings.xml dependency:go-offline

COPY src ./src
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml,required=true mvn -B -s /root/.m2/settings.xml package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/target/secret-safe-demo.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Tên artifact secret-safe-demo.jar phải khớp finalName/output thực của project. Dockerfile ví dụ không COPY settings.xml và không ARG REPO_PASSWORD.

Build bằng BuildKit/Buildx:

~~~bash
docker buildx build --secret id=maven_settings,src="$HOME/.m2/settings.xml" -t secret-safe-demo:local .
~~~

Secret file được cấp từ build client và mount trong thời gian thực thi đúng RUN instruction. Không cần đưa file settings vào Docker context. **Không** dùng cat /root/.m2/settings.xml, set -x, echo $REPO_PASSWORD hoặc copy file mount vào /workspace.

### 8.3. .dockerignore giảm nguy cơ đưa file nhạy cảm vào build context

Ví dụ cho Dockerfile tự build Maven bên trong:

~~~text
.git
.gradle
.mvn/wrapper/maven-wrapper.jar
**/.env
**/.env.*
**/secrets/**
**/*.pem
**/*.key
**/*.p12
**/*.jks
**/settings.xml
**/id_rsa*
**/id_ed25519*
target/
build/
~~~

Điều chỉnh theo project thật: nếu Dockerfile cần copy JAR đã build từ target/ hoặc build/, đừng exclude thư mục đó. .dockerignore là **hàng rào giảm build context**, không phải secret manager và không xóa file đã commit trong Git history.

Đối với project có .env.example, chỉ giữ tên biến và giá trị giả/empty; file .env có credential thật phải nằm ngoài context và được ignore.

### 8.4. Multi-stage không tự động làm mọi secret biến mất

Multi-stage giúp chỉ copy artifact cần thiết sang final stage, nhưng:

- Secret bị ghi vào JAR trong build stage vẫn được copy sang final image nếu nằm trong JAR.
- Secret bị ghi vào một filesystem layer/build cache vẫn có thể tồn tại trong cache dù không có trong final stage.
- Một lệnh RUN copy secret vào file rồi xóa ở lệnh sau vẫn có thể để lại bytes trong layer trước.
- Docker build logs, history, provenance và exported cache có thể chứa thông tin nếu lệnh build xử lý sai.

Vì vậy hãy **không ghi secret ra output**, scan final image và quản lý builder/cache retention. BuildKit secret mount bảo vệ đường truyền vào bước build; nó không thể ngăn chính chương trình build chủ động lưu secret.

## 9. Cloud Native Buildpacks và Spring Boot build-image

Spring Boot có thể tạo OCI image từ executable JAR bằng:

- Maven: spring-boot:build-image.
- Gradle: bootBuildImage.

Builder/buildpacks có thể nhận environment variables để tùy chỉnh Java version, proxy, buildpack behavior hoặc image generation. Các biến đó được cung cấp **cho builder**, không nên được dùng như kho chứa production secrets.

### 9.1. Chỉ dùng build environment cho giá trị không nhạy cảm

Ví dụ Gradle Groovy DSL:

~~~groovy
tasks.named('bootBuildImage') {
    environment['BP_JVM_VERSION'] = '17'
}
~~~

BP_JVM_VERSION là buildpack option không nhạy cảm. Không đặt DATABASE_PASSWORD, API_TOKEN, private key hoặc registry token trong environment. Buildpack có thể đọc environment, ghi log, ghi vào layer hoặc cache tùy implementation.

Tương tự, Maven Spring Boot Plugin có cấu hình image.env; chỉ truyền giá trị buildpack không nhạy cảm. Đừng đưa runtime production secret vào builder chỉ vì plugin hỗ trợ biến môi trường.

### 9.2. Bindings không tự trở thành secret-safe

Spring Boot Gradle bootBuildImage hỗ trợ bindings để mount volume/path vào builder container. Nếu một buildpack hỗ trợ service binding tương ứng, có thể cấp file tạm ngoài repository và mount read-only:

~~~groovy
tasks.named('bootBuildImage') {
    // Chỉ là ví dụ bind mount; buildpack phải hỗ trợ contract tại đích này.
    bindings = ['/run/ci-secrets/repository-binding:/platform/bindings/repository:ro']
}
~~~

Thư mục binding cần có cấu trúc/metadata mà buildpack cụ thể hiểu được. Mount :ro chỉ ngăn builder ghi ngược vào nguồn; nó **không** ngăn buildpack đọc rồi copy secret vào layer/cache. Kiểm tra buildpack docs, source và output; dùng token ngắn hạn, quyền chỉ đọc và file tạm ngoài build context.

### 9.3. Không nhầm buildpack variables với runtime secrets

Một số buildpacks (ví dụ Paketo) hỗ trợ biến BPE_* để ghi environment modifications vào image và áp dụng cho mọi deployment. Đây là cách cấu hình runtime environment **được lưu trong image**, chỉ dùng cho non-secret settings. Nếu cần database password/token, cấp ở runtime bằng secret manager hoặc file mount.

### 9.4. Registry credentials khi pull/publish image

Spring Boot plugin có docker.builderRegistry để xác thực khi pull builder/run image riêng tư và docker.publishRegistry khi publish image. Credential phải được cấp từ CI secret store, không viết literal vào build.gradle hoặc POM.

Gradle Groovy minh họa cho task bootBuildImage:

~~~groovy
tasks.named('bootBuildImage') {
    docker {
        publishRegistry {
            username.set(providers.environmentVariable('REGISTRY_USER'))
            password.set(providers.environmentVariable('REGISTRY_PASSWORD'))
        }
    }
}
~~~

CI phải cấp REGISTRY_USER/REGISTRY_PASSWORD ngay trong job publish. Không bật log debug/scan công khai có thể hiển thị configuration; giới hạn quyền đọc Gradle cache và CI logs. Tốt hơn nữa là dùng token ngắn hạn và scope chỉ push vào đúng repository.

Maven plugin có cấu hình image.publishRegistry tương ứng. Hãy dùng biến môi trường/CI secret mechanism theo cấu hình plugin đang dùng, không hard-code. Docker registry credential khác với credential để tải Maven dependency; không tái sử dụng cùng một token cho cả hai.

## 10. Keystore, TLS private key và signing key

### 10.1. TLS private key

Không đặt server.p12, server.key, client.key hoặc passphrase vào src/main/resources, vì chúng có thể đi vào BOOT-INF/classes, WEB-INF/classes hoặc image filesystem. Thay vào đó:

1. Lưu private key/keystore trong secret manager hoặc HSM/KMS theo policy.
2. Khi deploy, mount file vào đường dẫn chỉ app user đọc được, ví dụ /run/secrets/server.p12.
3. Đưa đường dẫn file và property name vào non-secret config.
4. Đưa passphrase vào secret file/runtime secret provider.
5. Hạn chế quyền filesystem, không copy file vào thư mục làm việc hoặc log nội dung.

### 10.2. Signing và encryption keys

Private key ký JAR, ký container image hoặc mã hóa dữ liệu không nên nằm trong builder image, application JAR hay final image. Ưu tiên:

- HSM/KMS/remote signing service, nơi private key không xuất ra file.
- CI identity có quyền yêu cầu ký đúng artifact, chỉ trong release job.
- Key ngắn hạn/ủy quyền theo workload identity nếu nền tảng hỗ trợ.
- Detached signature/attestation lưu như artifact phát hành riêng, theo quy trình xác minh.
- Audit ai yêu cầu ký, artifact digest nào được ký và thời điểm nào.

Nếu bắt buộc dùng file private key, chỉ mount vào signing step, giới hạn quyền đọc, không lưu trong workspace cache hoặc artifact output, rồi thu hồi/rotate theo lifecycle. **Không đóng private key vào image để ứng dụng có thể tự ký tùy ý.**

## 11. Kiểm tra JAR/WAR trước khi publish

### 11.1. Kiểm tra tên file và đường dẫn đáng ngờ

Liệt kê entries của executable JAR:

~~~bash
jar tf target/secret-safe-demo.jar
~~~

Tìm các tên có thể liên quan secret (chỉ in đường dẫn, không in nội dung):

~~~bash
jar tf target/secret-safe-demo.jar | grep -Ei '(^|/)(\.env[^/]*|.*\.(pem|key|p12|jks)|settings\.xml|credentials[^/]*|secrets?[^/]*)$'
~~~

Đây là kiểm tra sơ bộ. Tên file lạ là tín hiệu cần xem xét; file secret có thể được đổi tên thành .properties, .dat, .bin hoặc đặt trong package bất kỳ.

### 11.2. Scan nội dung archive, kể cả nested JAR

Một Spring Boot executable JAR có BOOT-INF/classes/ và nested JARs trong BOOT-INF/lib/. jar tf outer.jar chỉ cho thấy nested JAR filename, **không đọc nội dung bên trong các JAR đó**.

Quy trình scan:

1. Extract outer archive vào thư mục tạm cách ly.
2. Scan resource/class text files với secret scanner có chế độ redact.
3. Recursively inspect nested JAR/WAR nếu scanner không tự mở archive lồng nhau.
4. Kiểm tra application.properties, YAML, JSON, XML, .env, keystore filenames, PEM/SSH key headers và generated build metadata.
5. Không ghi matched secret vào CI logs hoặc ticket. Chỉ lưu file path, rule, commit/artifact digest và redacted context.
6. Xóa thư mục tạm theo policy sau khi hoàn tất.

Không dùng lệnh unzip -p hoặc cat trên file nghi chứa secret rồi để output vào CI logs. Nếu cần xác nhận, dùng scanner trả kết quả đã che giá trị hoặc xử lý trong môi trường kiểm soát.

### 11.3. WAR và các loại archive khác

Với WAR, kiểm tra WEB-INF/classes/, WEB-INF/lib/, META-INF/, WEB-INF/web.xml, deployment descriptors và nested libraries. Với EAR hoặc distribution ZIP, scan tất cả archive bên trong. Đừng giới hạn kiểm tra vào tên BOOT-INF vì layout khác nhau giữa JAR/WAR/executable archive.

## 12. Kiểm tra OCI image, history và build cache

Secret có thể nằm trong nhiều nơi khác nhau của image:

- Image config/environment variables.
- Layer filesystem, kể cả layer đã bị che bởi layer mới.
- Dockerfile instruction/history và build provenance.
- Image labels, build metadata, SBOM/attestation nếu custom tooling đưa value vào.
- CNB buildpack launch layer, cache layer hoặc workspace nếu buildpack đã lưu credential.
- Registry artifact cũ theo digest/tag, bản image trong mirror hoặc cache của runner.

### 12.1. Những lệnh kiểm tra cần dùng thận trọng

Các lệnh sau có thể hiển thị thông tin nhạy cảm nếu image đã bị cấu hình sai:

~~~bash
docker history --no-trunc secret-safe-demo:local
docker image inspect secret-safe-demo:local
docker save secret-safe-demo:local -o secret-safe-demo-image.tar
~~~

Chạy trong terminal/CI job có quyền hạn phù hợp. **Không dán nguyên output** vào chat, ticket hoặc log công khai vì history/config có thể chứa credential đã lộ. Dùng scanner image-aware với redaction để kiểm tra image config và layer filesystem; kiểm tra provenance/attestation riêng nếu pipeline tạo chúng.

### 12.2. docker save và các layer cũ

Một file bị xóa ở layer mới có thể vẫn nằm trong layer cũ của image. Vì vậy chỉ kiểm tra filesystem cuối cùng của container có thể bỏ sót secret. Cần scanner hiểu OCI/Docker layers, hoặc export image rồi kiểm tra từng layer theo cách không in secret.

Nếu phát hiện secret trong một image đã push, xóa tag hoặc push image mới **không tự làm credential cũ mất hiệu lực**. Registry có thể giữ blobs/digests cũ cho đến khi retention/garbage collection chạy; mirror và cache runner cũng có thể còn bản copy. Phải revoke/rotate secret và xử lý artifact/registry theo incident policy.

### 12.3. CNB build cache và Maven/Gradle caches

Nếu buildpack hoặc custom task ghi secret vào cached layer/output, dữ liệu có thể còn trong:

- CNB build cache/launch cache/workspace volumes.
- Docker/BuildKit cache.
- Gradle local/remote build cache.
- Maven local repository hoặc CI workspace.
- CI artifacts và test reports.

Không ghi secret vào output được cache. Nếu đã ghi, xử lý cache như một bản sao của secret: giới hạn truy cập, xóa/expire đúng scope và rotate credential. Không dùng docker system prune --volumes hoặc xóa toàn bộ cache của shared runner một cách tùy tiện; làm theo owner/retention policy và xác định chính xác cache chứa dữ liệu.

## 13. Git, .gitignore, .dockerignore và secret scanning

### 13.1. Hai ignore files có hai phạm vi khác nhau

| File | Tác dụng | Không làm được |
| --- | --- | --- |
| .gitignore | Ngăn file chưa track được thêm vào Git theo pattern. | Không xóa file đã commit, branch/tag/fork hoặc Git history. |
| .dockerignore | Loại file khỏi Docker build context gửi tới builder. | Không ngăn file đã được COPY từ stage khác hoặc xóa nội dung trong Git/image cũ. |
| CI artifact exclude | Ngăn file khỏi artifact upload theo rule. | Không xóa log/cache/image đã publish trước đó. |

Một .dockerignore khởi đầu có thể là:

~~~text
.git
**/.env
**/.env.*
**/secrets/**
**/*.pem
**/*.key
**/*.p12
**/*.jks
**/settings.xml
**/id_rsa*
**/id_ed25519*
~~~

Hãy điều chỉnh theo cấu trúc project. Đừng ignore một file cần thiết cho build chỉ để làm pipeline pass; thay bằng secret mount hoặc một đường dẫn ngoài build context.

### 13.2. Secret scanning nhiều thời điểm

Chạy scanner ở nhiều điểm:

- **Pre-commit/IDE:** phát hiện sớm token/key được paste vào source.
- **Pull request/CI:** scan changed files và source tree.
- **Git history:** scan cả commit history, branch/tag nếu policy yêu cầu.
- **Archive:** scan JAR/WAR và nested archives sau package.
- **Image:** scan config, metadata, layers và final filesystem trước publish.
- **Runtime/logs:** detect credential patterns, access bất thường và secret bị in ra log.

Dùng scanner được tổ chức phê duyệt (ví dụ Gitleaks, TruffleHog hoặc scanner tích hợp platform) với output redacted. Không tắt rule chỉ vì secret scanner tạo false positive; phân loại, suppress theo path/rule có lý do và review định kỳ.

### 13.3. Không chỉ tìm theo tên file

Secret có thể được serialize thành JSON/YAML/properties, base64, URL-encoded, split thành nhiều phần hoặc nhúng trong class constants. Scanner cần nhận diện nhiều loại token/key và kiểm tra archive/image. Một regex tìm .pem không phát hiện được password trong application.yml.

## 14. CI/CD: cấp credential đúng job, đúng bước

### 14.1. Tách identity theo quyền

Một pipeline có thể cần các identity riêng:

| Job/step | Quyền nên có | Không nên có |
| --- | --- | --- |
| Resolve dependency | Read-only tới repository cần thiết. | Deploy/publish permission. |
| Build application | Chỉ source/build inputs và build service cần thiết. | Production database credential. |
| Build image | Quyền pull builder/base image và build. | Runtime API token của ứng dụng. |
| Publish image | Push vào đúng registry/repository. | Quyền admin toàn registry. |
| Deploy | Quyền triển khai workload/đọc secret runtime. | Private signing key không liên quan. |
| Sign release | Yêu cầu HSM/KMS ký digest đã được phê duyệt. | Export private key sang workspace. |

Dùng workload identity/OIDC hoặc short-lived tokens nếu nền tảng hỗ trợ. Tách token download dependency, publish image và deploy; đặt expiration, audience và repository scope phù hợp.

### 14.2. Log và shell

Không làm:

~~~bash
echo "$REGISTRY_PASSWORD"
env
set -x
mvn -X deploy
./gradlew --debug publish
~~~

Những lệnh trên có thể in environment, command expansion hoặc request/config detail. Debug log chỉ bật tạm trong môi trường hạn chế và cần kiểm tra/redact trước khi lưu. Masking của CI là lớp hỗ trợ; nó không bảo đảm che được token bị encode, chia nhỏ, escape hoặc in trong dạng khác.

### 14.3. Workspace và artifacts

- Dùng runner/agent riêng cho job nhạy cảm; không chia sẻ workspace writable với job không tin cậy.
- Đặt file credential ngoài repository và Docker build context.
- Hạn chế retention của temporary settings, key files, reports và cache.
- Không upload .m2/settings.xml, gradle.properties, .env, keystore hoặc secret mount source như build artifact.
- Xóa file tạm trong finally/post-job cleanup, nhưng nhớ **xóa file không thay thế revoke credential** nếu file từng bị copy/log.
- Bảo vệ build logs, test reports, Gradle configuration cache và Docker daemon/registry access.

## 15. Ví dụ workflow đầy đủ: Maven build, JAR và runtime secret

### 15.1. Source tree

~~~text
secret-safe-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
├── src/main/java/com/example/security/SecretSafeApplication.java
├── src/main/java/com/example/security/PartnerApiProperties.java
└── src/main/resources/application.properties
~~~

Không có settings.xml, .env, .pem, .key, keystore hoặc application-prod.yml chứa credential trong project.

### 15.2. Resource chỉ chứa cấu hình không nhạy cảm

src/main/resources/application.properties:

~~~properties
spring.config.import=configtree:/run/secrets/
partner.api.base-url=https://api.partner.example
server.port=8080
~~~

File này được đóng trong JAR nhưng không có token/password. Khi runtime platform mount /run/secrets/partner.api.token, Spring Boot cung cấp property partner.api.token.

### 15.3. Java application và properties class

SecretSafeApplication.java:

~~~java
package com.example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class SecretSafeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecretSafeApplication.class, args);
    }
}
~~~

PartnerApiProperties.java:

~~~java
package com.example.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    private String baseUrl;
    private String token;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }
}
~~~

Code sử dụng getToken() khi tạo Authorization header cho client. **Không log object, token, Authorization header hoặc exception request đã gắn header**. Không tạo toString() có chứa token.

### 15.4. Maven build credentials

CI tạo/cung cấp user settings bên ngoài project, dùng <server><id>internal-releases</id>... tương ứng repository ID. Token chỉ có quyền đọc dependency và được thu hồi/expire sau job. Không copy settings vào src/main/resources hoặc Docker context.

### 15.5. Build Docker với secret mount

Dùng Dockerfile ở mục 8.2. Lệnh docker buildx build --secret ... mount settings trong đúng các lệnh Maven cần resolve private dependencies. JAR đầu ra chỉ chứa code và non-secret resources.

### 15.6. Cấp runtime secret

Khi deploy, platform mount secret file vào /run/secrets/partner.api.token, quyền đọc chỉ cấp cho user chạy Java. configtree: nạp giá trị vào Spring Environment. Runtime container không cần Maven settings hoặc registry publishing token.

Nếu thiếu token bắt buộc, app nên fail fast theo cấu hình production. Không đưa token giả mặc định vào application.properties để che lỗi deploy; test phải dùng credential giả riêng.

## 16. Ví dụ kiểm tra registry credentials với Gradle BootBuildImage

Một project Gradle có thể cấu hình bootBuildImage để publish image. Dùng secret-backed environment variables do CI cấp, ví dụ:

~~~groovy
tasks.named('bootBuildImage') {
    docker {
        publishRegistry {
            username.set(providers.environmentVariable('REGISTRY_USER'))
            password.set(providers.environmentVariable('REGISTRY_PASSWORD'))
        }
    }
}
~~~

Không commit giá trị thật trong build.gradle. CI chỉ expose hai biến trong job publish; job compile/test không cần chúng. Không in provider values hoặc task configuration ra logs. Khi có configuration cache, bảo vệ GRADLE_USER_HOME và cache encryption key theo policy.

Nếu registry hỗ trợ workload identity/token ngắn hạn, dùng token phù hợp thay password dài hạn. Builder registry credentials (pull builder/run image) và publish registry credentials (push output image) có thể là hai identity khác nhau; cấp đúng quyền và scope.

## 17. Kiểm tra trước khi publish: checklist nhiều tầng

### 17.1. Source và repository

- [ ] Không có credential literal trong Java/Kotlin/Scala source, YAML, properties, XML, shell script, Dockerfile hoặc test.
- [ ] Không có private key/keystore trong source tree.
- [ ] .gitignore và secret scanner được cấu hình; scan Git history theo policy.
- [ ] settings.xml/gradle.properties chứa credential không được commit.
- [ ] CI dùng secret store/short-lived token và không echo giá trị.

### 17.2. Build và resource processing

- [ ] Maven filtering chỉ áp dụng cho allowlist non-secret resources.
- [ ] Gradle processResources/expand không nhận secret properties.
- [ ] Không có task ghi secret vào build output, generated source, test report hoặc build cache.
- [ ] Private repository credentials chỉ có read permission cần thiết.
- [ ] Maven/Gradle debug logs/build scans không chứa credential.

### 17.3. Archive

- [ ] JAR/WAR không chứa .env, settings.xml, .pem, .key, .p12, .jks hoặc config production có secret.
- [ ] Đã scan BOOT-INF/classes, WEB-INF/classes, resources và nested JARs.
- [ ] Đã scan file text/config với secret scanner redacted, không chỉ kiểm tra filename.
- [ ] Không có build-generated metadata, manifest hoặc test resource chứa token.
- [ ] Archive đúng phiên bản/commit và đã được ký/attest theo release policy.

### 17.4. Docker/CNB image

- [ ] Không dùng ARG/ENV để truyền password/token/private key trong Dockerfile.
- [ ] Không COPY settings/secret files vào image hoặc build context.
- [ ] BuildKit secret/SSH mount chỉ được sử dụng ở RUN step cần thiết; command không copy/echo secret.
- [ ] CNB buildpack environment chỉ chứa build options không nhạy cảm.
- [ ] Nếu dùng bindings, buildpack contract đã được kiểm tra và secret không bị ghi vào layer/cache.
- [ ] Đã scan image config, history, filesystem layers, labels và provenance với output redacted.
- [ ] Không có secret trong build cache/launch cache/workspace hoặc CI artifacts.
- [ ] Registry credentials chỉ có quyền cần thiết, được cấp trong đúng job.

### 17.5. Runtime và vận hành

- [ ] Secret được cấp qua secret manager hoặc file mount; quyền đọc giới hạn.
- [ ] spring.config.import=configtree: trỏ đúng mount path.
- [ ] Secret bắt buộc không dùng optional: trong production.
- [ ] Actuator/diagnostic endpoints được bảo vệ; không lộ Environment/configuration.
- [ ] Logs không chứa password, token, Authorization header, private key hoặc full connection string.
- [ ] Có rotation/revocation owner, expiration, audit trail và incident runbook.

## 18. Tình huống lỗi và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| jar tf thấy application-prod.yml hoặc .env. | Resource production bị copy vào archive. | Mở đúng file trong môi trường kiểm soát, rotate nếu có secret, chuyển sang runtime external config và rebuild. |
| BOOT-INF/classes/application.properties có password. | Hard-code hoặc resource filtering thay placeholder bằng secret. | Bỏ secret khỏi filter/source, scan lại target/classes và JAR. |
| Secret không có trong source nhưng xuất hiện trong JAR. | Maven/Gradle task sinh resource hoặc manifest chứa giá trị. | Kiểm tra process-resources, processResources, generated files và plugin config. |
| Docker history hiển thị token. | Dùng ARG, shell command hoặc RUN có credential. | Revoke token, chuyển sang BuildKit secret/SSH mount, rebuild image và xử lý image/cache cũ. |
| docker inspect thấy password trong Config.Env. | Dùng Dockerfile ENV hoặc publish config bị lưu vào runtime env. | Rotate password, loại khỏi image config, cấp runtime secret ngoài image. |
| Image cuối không thấy file secret nhưng scanner tìm trong layer cũ. | Secret được copy ở layer trước rồi xóa ở layer sau. | Rebuild từ clean context, xử lý old image/cache/registry blobs và rotate credential. |
| BuildKit secret mount dùng đúng nhưng image vẫn lộ token. | Lệnh trong RUN đã copy token vào output, generated file hoặc logs. | Sửa build command; mount không thể ngăn ứng dụng build ghi secret ra nơi khác. |
| bootBuildImage log chứa API token. | Truyền token qua builder environment hoặc buildpack log biến. | Rotate token, bỏ secret khỏi builder env, dùng binding/secret mechanism được buildpack hỗ trợ. |
| CNB image cache chứa private settings. | Buildpack/custom build task đã lưu file credential vào cached layer/workspace. | Rotate, xóa cache đúng phạm vi theo policy, sửa buildpack/task để không cache secret. |
| Maven resolve private repository thất bại. | Server ID sai, settings không được cấp hoặc credential hết hạn. | Kiểm tra repository ID/secret injection; không paste password vào POM hoặc command line. |
| Gradle báo thiếu repository credentials. | Tên repository/property prefix không khớp hoặc CI chưa expose biến. | Xác nhận internalUsername/internalPassword mapping và secret scope; không thêm literal vào script. |
| Maven encrypted password bị hiểu là an toàn tuyệt đối. | Maven 3 encryption chỉ obfuscation-grade. | Bảo vệ settings/master file và dùng CI secret manager; không commit cả hai. |
| Spring Boot không bind được token. | File name/path không khớp property hoặc spring.config.import sai. | Xác nhận mount path, filename/property mapping và startup error; không thêm token vào archive để chữa. |
| Container khởi động nhưng kết nối DB thất bại. | Secret không mount, permission sai hoặc property source bị override. | Kiểm tra secret mount/permissions và property precedence, không in password ra log. |
| Secret scanner báo false positive. | File test/example chứa chuỗi trông giống token. | Xác nhận đó là fixture giả, suppress theo rule/path có lý do và giữ scanner hoạt động. |
| Credential bị phát hiện trong Git history. | File đã commit trước khi ignore. | Revoke/rotate ngay, rà soát access/logs, rồi xử lý history/forks theo kế hoạch. |
| Image cũ vẫn còn trong registry sau khi push bản mới. | Tag mới không xóa digest/blob cũ hoặc mirror/cache còn giữ bản. | Thu hồi credential trước; áp dụng retention/garbage collection và kiểm tra mirror/cache. |
| Token xuất hiện trong CI log. | echo, set -x, debug mode, exception hoặc scanner in raw match. | Rotate/revoke, hạn chế log access, redact/handle log theo policy và sửa pipeline. |

## 19. Incident response khi secret đã lọt vào archive/image/Git

Nếu phát hiện credential thật trong JAR, image, cache, source hoặc log, xử lý theo thứ tự:

1. **Xác định loại secret và phạm vi quyền.** Token đọc repository khác với production DB admin password; đánh giá quyền, audience, scope và hệ thống có thể truy cập.
2. **Revoke/rotate ngay.** Tạo credential mới, cập nhật secret manager/deployment, kiểm tra credential cũ không còn dùng được. Xóa file khỏi image không thu hồi quyền của token.
3. **Containment.** Hạn chế quyền registry/artifact/log/cache có bản lộ; ngăn image cũ tiếp tục deploy/pull nếu policy yêu cầu.
4. **Rebuild sạch.** Sửa source/build config, tạo archive/image mới từ input sạch, scan lại mọi layer và nested archive.
5. **Xử lý bản sao.** Xem xét Git history, branches/forks, registry digests, mirrors, CI artifacts, Docker/BuildKit/CNB caches, Gradle/Maven caches và logs.
6. **Audit.** Rà soát ai có thể đọc secret, thời gian lộ, access logs và hành vi sử dụng credential trong khoảng thời gian đó.
7. **History rewrite nếu cần.** Chỉ thực hiện sau khi đã rotate và phối hợp owner/reviewer; rewrite Git history ảnh hưởng clones/forks/commit references. Không coi rewrite là bước thay thế rotation.
8. **Phòng ngừa tái diễn.** Thêm scanner/rule, giảm quyền/TTL, tách secret store, sửa build task và cập nhật runbook.

Nếu secret trong log phải được xử lý, tuân thủ audit retention và incident policy; hạn chế truy cập, redact theo quy trình, không xóa log tùy tiện để che dấu vết. Lưu bằng chứng đã redacted, không sao chép plaintext secret vào ticket.

### 19.1. Vì sao “xóa secret khỏi image” chưa đủ?

- Image layer cũ có thể còn bytes dù filesystem cuối không hiển thị file.
- Registry có thể lưu digest/blob cũ sau khi tag mới được push.
- Docker daemon/remote cache/CI artifact có thể còn bản copy.
- Git history, forks và local clones có thể giữ commit chứa secret.
- Credential có thể đã bị người khác đọc trong thời gian lộ.

**Rotation/revocation là biện pháp thu hồi quyền.** Xóa các bản sao giúp giảm khả năng tiếp tục bị sử dụng và giảm tái phát, nhưng không thay thế việc vô hiệu credential đã lộ.

## 20. Bài thực hành và tiêu chí đạt

### Bài A — runtime secret với Spring Boot config tree

1. Tạo Spring Boot Java 17 app với PartnerApiProperties và SecretSafeApplication.
2. Đặt spring.config.import=configtree:/run/secrets/ trong application.properties.
3. Tạo file secret giả trong thư mục test tạm với tên partner.api.token; không dùng token thật.
4. Khởi động app trong môi trường test có mount config tree.
5. Kiểm tra properties bind được mà token không xuất hiện trong log/HTTP response.
6. Xác nhận JAR chỉ chứa tên config/path non-secret, không chứa secret file hoặc giá trị giả đã được copy thành resource.

### Bài B — Maven resource filtering và repository credentials

1. Cấu hình hai resource directories: unfiltered main resources và filtered non-secret build metadata.
2. Đưa repository credentials vào user/CI settings.xml, server ID khớp repository ID.
3. Cấp credential qua CI secret store/environment, không commit settings.
4. Chạy mvn clean package và scan target/classes cùng executable JAR.
5. Kiểm tra filter file, effective settings/logs và archive không chứa password/token.
6. Ghi lại vì sao Maven 3 password encryption không thay secret manager.

### Bài C — Gradle repository credentials

1. Khai báo private repository bằng credentials(PasswordCredentials) và repository name rõ ràng.
2. Cấp internalUsername/internalPassword qua ORG_GRADLE_PROJECT_... trong CI.
3. Không ghi credential vào project gradle.properties hoặc build script.
4. Chạy dependency resolution và scan build/resources/main/Boot JAR.
5. Bảo vệ Gradle user home/configuration cache; xác nhận build logs không in credential.

### Bài D — Docker BuildKit secret

1. Tạo Maven Dockerfile multi-stage ở mục 8.2.
2. Tạo .dockerignore loại settings, .env, secret directories, private keys.
3. Dùng docker buildx build --secret ... để mount settings chỉ trong RUN Maven.
4. Xác nhận final image không chứa settings/private key.
5. Kiểm tra image history/config/layers với scanner redacted.
6. Thử trên branch riêng một Dockerfile sai dùng ARG/ENV bằng token giả, xem vì sao scanner phát hiện; không dùng credential thật để thử.

### Bài E — CNB và registry auth

1. Cấu hình bootBuildImage/spring-boot:build-image với builder option không nhạy cảm.
2. Tách buildpack environment khỏi runtime secrets.
3. Nếu cần binding, mount file tạm read-only ngoài source tree và xác nhận buildpack support/không lưu vào cache.
4. Cấp registry push token chỉ cho job publish.
5. Scan image/cache/logs sau build; xác minh không có token hoặc private key.

### Checklist cuối

- [ ] Không có secret literal trong source, POM, Gradle script, Dockerfile hoặc resource.
- [ ] .gitignore/.dockerignore được cấu hình đúng nhưng không bị coi là secret manager.
- [ ] Maven/Gradle resource filtering không đưa secret vào output.
- [ ] Maven repository credentials nằm trong external settings/CI secret store.
- [ ] Gradle dùng typed credentials và secret-backed properties/environment.
- [ ] Không truyền secret bằng Docker ARG/ENV, không COPY settings/key vào image.
- [ ] Docker BuildKit secret/SSH mount chỉ có scope một build step.
- [ ] Hiểu multi-stage không tự loại secret đã ghi vào cache/layer.
- [ ] CNB builder environment không chứa runtime secret; bindings được kiểm tra theo buildpack contract.
- [ ] Spring Boot đọc runtime secret từ config tree/file mount hoặc secret manager.
- [ ] Private key/keystore không nằm trong BOOT-INF/classes, WEB-INF/classes hoặc image filesystem.
- [ ] Không log token, password, Authorization header hoặc toàn bộ config object.
- [ ] Scan Git history, JAR/WAR, nested archives, OCI image/config/history và cache.
- [ ] Có quy trình revoke/rotate, audit và incident response khi phát hiện leak.
- [ ] Có test với secret giả và xác nhận output không chứa giá trị test.

**Tiêu chí hoàn thành:** một executable JAR/WAR và OCI image đã qua kiểm tra không chứa credential/private key/cấu hình production nhạy cảm; build có thể resolve private dependencies và publish image bằng credential tạm thời ngoài artifact; runtime nhận secret qua config tree/secret manager; scan report đã redact; và người học giải thích được cách revoke/rotate nếu một secret từng bị lộ. Nếu chưa có Docker/CI/secret manager thật, mô tả bước chưa kiểm chứng và dùng dữ liệu giả, không đánh dấu security gate PASS chỉ dựa vào source review.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Docker — Build Secrets](https://docs.docker.com/build/building/secrets/)
- [Docker — Dockerfile ARG and ENV](https://docs.docker.com/reference/dockerfile/)
- [Docker — SecretsUsedInArgOrEnv Build Check](https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/)
- [Apache Maven — Settings and Server Credentials](https://maven.apache.org/settings.html)
- [Apache Maven — Password Encryption](https://maven.apache.org/guides/mini/guide-encryption.html)
- [Apache Maven — Resource Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Gradle — Handling Repository Credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html)
- [Gradle — Build Environment and Project Properties](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Cloud Native Buildpacks — Build-time Environment Variables](https://buildpacks.io/docs/for-platform-operators/how-to/build-inputs/build-env/)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

**Ghi nhớ:** archive/image là artifact có thể được copy, scan, cache, push và giữ lại lâu dài. Vì vậy **secret chỉ nên được cấp ở đúng bước cần dùng**, runtime secret phải được inject lúc deploy, và mọi archive/image cần được scan trước khi phát hành. Nếu một credential đã lọt vào Git, JAR, image, cache hoặc log, hãy **revoke/rotate trước**, rồi mới xử lý các bản sao và rebuild sản phẩm.