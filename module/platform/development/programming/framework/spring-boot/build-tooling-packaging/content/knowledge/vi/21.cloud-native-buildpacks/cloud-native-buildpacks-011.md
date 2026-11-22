# Xác thực kho image riêng và cấu hình xuất bản image

Spring Boot có thể tạo **OCI container image bằng Cloud Native Buildpacks (CNB)** với Maven `spring-boot:build-image` hoặc Gradle `bootBuildImage`, không cần tự viết Dockerfile. Việc build thành công trên máy không đồng nghĩa image đã được đưa lên **registry riêng tư**. Khi doanh nghiệp sử dụng private registry, cần phân biệt chính xác việc **pull builder/run image**, việc **push ứng dụng**, **quyền của từng identity**, **tên image đích**, **thời điểm publish** và **bằng chứng image đã xuất bản**.

**Ghi nhớ:** Trong Spring Boot 3.3, `docker.builderRegistry` dành cho việc xác thực lúc lấy builder/run images riêng tư; `docker.publishRegistry` dành cho việc xác thực lúc phát hành generated application image. Registry đích khi push được chọn từ **host trong image name** (`registry.example.com/team/cnb-registry-demo:1.0.0`), không phải chỉ từ `publishRegistry.url`. Bật `publish` ở Maven hay `--publishImage` ở Gradle mới yêu cầu plugin push. Image nằm trong Docker daemon mà chưa push thì chưa phải artifact đã xuất bản.

Bài học cố định ví dụ ở **Java 17, Spring Boot 3.3.13, Maven 3.9.x hoặc Gradle tương thích**. Các hostname `registry.example.com`, `mirror.corp.example` và package `dev.example` là giá trị minh họa, **không** phải kho đang hoạt động. Chỉ thực thi thao tác push khi có quyền, có registry thật và secret store. Các version được pin để giải thích nhất quán, không phải khẳng định đây là release mới nhất.

## 1. Kiến trúc của CNB image và các điểm xác thực

Spring Boot plugin kết nối Docker-compatible daemon, tạo build container từ CNB builder, dùng buildpacks và lifecycle để sinh một application image. Builder image có buildpacks/lifecycle; run image là nền runtime; application image là sản phẩm được triển khai.

```text
                         Java source / Maven / Gradle
                                     |
                                     v
                            Spring Boot plugin
                                     |
                                     v
                              Docker daemon
                                     |
             +-----------------------+-------------------+
             |                                           |
             v                                           v
  Private builder registry                      Private run registry
  pull builder image                            pull run image
  docker.builderRegistry                        docker.builderRegistry
             |                                           |
             +-----------------------+-------------------+
                                     |
                                     v
                          CNB builder/lifecycle
                                     |
                                     v
                             Application image
                 registry.example.com/team/cnb-registry-demo:1.0.0
                                     |
                           publish=true / --publishImage
                                     |
                                     v
                           Private application registry
                           docker.publishRegistry
                                     |
                                     v
                           Remote manifest digest
                                     |
                          pull identity of runtime
                                     |
                                     v
                             Kubernetes / Docker
```

| Hoạt động | Cần quyền | Credential domain | Kết quả cần kiểm tra |
| --- | --- | --- | --- |
| Pull builder image | `read/pull` | Registry chứa builder | Builder image có đúng tag/digest |
| Pull run image | `read/pull` | Registry chứa run image | Run image tương thích builder stack |
| Push ứng dụng | `write/push` | Registry nơi image application được publish | Manifest/layers đã được chấp nhận |
| Pull khi triển khai | `read/pull` | Identity của Pod/host triển khai | Deployment thực sự kéo được image |
| Verify image | `read/inspect` | Registry sau publish | Image digest khớp release record |

**Không dùng một token writer để làm mọi việc.** CI account chỉ cần pull builder/run và push đúng application repository; runtime cluster chỉ cần pull artifact cuối. Quyền writer nên có phạm vi namespace/repository hẹp, không có admin role.

### 1.1. Ba loại image có thể dùng các registry khác nhau

```text
mirror.corp.example/buildpacks/java-builder:approved
mirror.corp.example/buildpacks/java-run:approved
registry.example.com/team/cnb-registry-demo:1.0.0
```

Hai reference đầu dành cho CNB lifecycle, reference cuối là image của ứng dụng. Nếu builder/run nằm ở một private host và app ở host khác, token publish app **không** tự giúp kéo builder. Ngược lại, token pull builder thường **không** được cấp push vào application repository.

Nếu builder image được cấu hình trỏ đến default run image trong metadata, `runImage` có thể để mặc định. Chỉ override khi doanh nghiệp chủ động mirror run image **và** bảo đảm stack/run-image compatibility. Tùy cơ chế registry và plugin, khi builder/run nằm trên nhiều registry khác nhau có thể cần nhiều auth identities hoặc daemon credential helpers; đừng mặc định một bộ `builderRegistry` credentials truy cập được mọi host.

### 1.2. Docker daemon khác Docker registry

| Thành phần | Nhiệm vụ | Lỗi tiêu biểu |
| --- | --- | --- |
| Docker daemon | Chạy builder container, quản lý image local, cung cấp Docker API | `Cannot connect to the Docker daemon` |
| Docker registry | Nhận push/pull và lưu OCI manifests/layers | `unauthorized`, `denied`, `manifest unknown` |
| Maven/Gradle plugin | Gọi CNB/Docker API, chọn image name, cấp registry credentials | Sai tên, thiếu publish flag |
| CI runner | Cấp JDK, checkout source, secrets, Docker socket, network | Không có token hoặc quyền publish |
| Kubernetes runtime | Pull image đã phát hành, khởi tạo Pod | `ErrImagePull`, `ImagePullBackOff` |

Lệnh `docker info` thành công chứng minh có daemon, **không chứng minh có quyền publish**. `docker login` thành công chỉ xác nhận một cơ chế đăng nhập registry, **không tự sửa lỗi thiếu daemon**.

## 2. Tên image quyết định registry đích

Một reference điển hình:

```text
registry.example.com:5000/team/cnb-registry-demo:1.0.0
|------ host:port -----|------ repository ------|tag|
```

Tên đầy đủ có registry host, namespace/repository và tag. Để xuất bản vào private registry, hãy đặt **cả ba**; không để plugin mặc định vào `docker.io/library/...` rồi chỉ thêm credentials cho kho nội bộ.

**Sai lầm thường gặp:** Cấu hình `docker.publishRegistry.url=registry.example.com` nhưng image name vẫn `docker.io/library/cnb-registry-demo:1.0.0`. Tài liệu chính thức Spring Boot 3.3 nêu rõ: trường `url` được chuyển tới registry-auth logic nhưng **không được dùng để quyết định đích publish**. Đích vẫn lấy từ registry part của tên image.

| Thông tin | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Host | `registry.example.com` | Nơi push |
| Namespace | `team` | Khu vực ACL/ownership |
| Repository | `cnb-registry-demo` | Sản phẩm |
| Tag | `1.0.0` hoặc full commit SHA | Tên có thể mutable |
| Digest | `@sha256:...` | Định danh manifest/index thực tế |

Dạng `@sha256:...` ở đây chỉ là **mẫu định dạng**, chưa chứa hash dùng được. Registry thường cho phép tag trỏ đến manifest khác nếu chưa bật immutability. Để rollback chính xác, nên lưu **verified registry digest**, không chỉ tag `latest`.

### 2.1. Những cách tag phổ biến

- `1.0.0`: phù hợp semantic release; cần cơ chế không cho overwrite hoặc phải lưu digest.
- `git-<short-sha>`: đọc gọn; có rủi ro va chạm về lâu dài nên provenance vẫn dùng full SHA.
- `git-<full-sha>`: rõ revision; nhưng hai build cùng commit chưa chắc byte image giống nhau.
- `run-<run-id>-<attempt>`: phân biệt CI rerun, cần cả repo/workflow/job namespace nếu sinh nhiều image.
- `latest`: dễ thử local nhưng không dùng để xác nhận chính xác production artifact.

Không nhét token/password vào image tag, OCI labels hoặc repository path; các giá trị đó có thể xuất hiện trong registry log và UI.

## 3. Hai phương án publish: plugin trực tiếp hay Docker push

### Phương án A — Spring Boot plugin build và push

Maven:

```bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-registry-demo:1.0.0 \
  -Dspring-boot.build-image.publish=true
```

Gradle:

```bash
./gradlew bootBuildImage \
  --imageName=registry.example.com/team/cnb-registry-demo:1.0.0 \
  --publishImage
```

Đây là các lệnh minh họa về **cách bật publish**, chỉ chạy được nếu daemon/registry/auth đã cấu hình. Với private registry, có thể cần khai báo `publishRegistry`; đừng kỳ vọng plugin tự dùng Docker CLI login trên mọi phiên bản/runner.

### Phương án B — Build local image rồi dùng Docker CLI push

```bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-registry-demo:1.0.0

docker image inspect registry.example.com/team/cnb-registry-demo:1.0.0
docker push registry.example.com/team/cnb-registry-demo:1.0.0
```

Phương án B dùng **Docker CLI credentials**, ví dụ `docker login --password-stdin`. Hữu ích khi policy yêu cầu scan/local smoke test/phê duyệt **trước** bước push. Nếu đã chọn plugin publish trực tiếp thì gọi `docker push` thêm thường là thừa.

**Mặc định plugin publish=false.** Image build xong và `docker images` nhìn thấy không đồng nghĩa remote registry có image. Sau push cần kiểm tra bằng remote pull/manifest digest.

## 4. Bài thực hành Spring Boot Java 17

Ta xây REST app nhỏ `cnb-registry-demo`. Endpoint `GET /status` trả về `cnb-ready`; dùng nó làm smoke test sau khi image đã push rồi pull lại.

### 4.1. Cấu trúc project

```text
cnb-registry-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/cnb/
    │   ├── CnbRegistryApplication.java
    │   └── StatusController.java
    └── test/java/dev/example/cnb/
        └── StatusControllerTest.java
```

Bạn có thể dùng Maven POM ở mục 5 **hoặc** Gradle `settings.gradle`/`build.gradle` ở mục 7 với **cùng source Java**. Không cần maintain cả hai build definitions trong cùng project nếu không có yêu cầu riêng.

### 4.2. Ứng dụng chính

`src/main/java/dev/example/cnb/CnbRegistryApplication.java`:

```java
package dev.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbRegistryApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbRegistryApplication.class, args);
    }
}
```

### 4.3. Controller

`src/main/java/dev/example/cnb/StatusController.java`:

```java
package dev.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/status")
    public String status() {
        return "cnb-ready";
    }
}
```

### 4.4. Kiểm thử bằng MockMvc

`src/test/java/dev/example/cnb/StatusControllerTest.java`:

```java
package dev.example.cnb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StatusControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void statusReturnsExpectedBody() throws Exception {
        mvc.perform(get("/status"))
                .andExpect(status().isOk())
                .andExpect(content().string("cnb-ready"));
    }
}
```

Đây là phép thử Spring context trên test classpath, **không** chứng minh OCI image đã build/push hoặc runtime image có thể chạy. Kiểm tra image và remote pull ở các mục sau là bước bổ sung bắt buộc.

## 5. Maven Spring Boot 3.3: POM đầy đủ để cấu hình publishRegistry

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>cnb-registry-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
                        <name>${env.IMAGE_NAME}</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                    <docker>
                        <publishRegistry>
                            <username>${env.REGISTRY_USER}</username>
                            <password>${env.REGISTRY_TOKEN}</password>
                        </publishRegistry>
                    </docker>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Cách đọc chính xác:**

1. `IMAGE_NAME` phải là **full target reference** như `registry.example.com/team/cnb-registry-demo:1.0.0`. Đừng để release dùng tên rỗng; CI phải kiểm tra biến trước lệnh build-image.
2. `REGISTRY_USER`/`REGISTRY_TOKEN` được lấy từ environment tại lúc Maven chạy. Đây là credential **push app**, không phải credential builder.
3. `BP_JVM_VERSION=17` là biến cấu hình cho Paketo Java buildpack, **không phải kênh gửi secret**. Không đặt token vào `image.env`; buildpack có thể log/ghi một số biến môi trường.
4. POM cố ý **không** đặt `<publish>true</publish>` làm mặc định. Chỉ release job được phép mới bật `-Dspring-boot.build-image.publish=true`.
5. Spring Boot starter parent quản lý versions và repackage goal. Goal `spring-boot:build-image` gọi CNB để tạo image; goal `build-image-no-fork` dùng khi archive đã có từ lifecycle trong cùng invocation.
6. Những biến `${env...}` ở POM là cú pháp Maven để lấy environment. **Ví dụ POM để build-image cần những biến đó**; nếu chưa thiết lập tên image/credentials, chỉ nên chạy test/package mà không publish. Trong môi trường doanh nghiệp, có thể tách Maven profile cho local/release để tránh cấu hình publish credentials khi không cần.

**Bảo mật:** Env injection không tự làm token bí mật trong mọi hoàn cảnh. Không in `env`, `help:effective-pom` (đặc biệt bản đã resolve secrets), `mvn -X` hoặc process environment trên runner dùng chung. Không commit credentials hay đưa token lên command-line `-Dpassword=...` trong job không kiểm soát.

### 5.1. Maven local kiểm tra Java và tạo image chưa publish

Sau khi Docker daemon có thể truy cập, ở Bash:

```bash
export IMAGE_NAME="registry.example.com/team/cnb-registry-demo:local"
mvn -B -ntp clean verify
mvn -B -ntp spring-boot:build-image
docker image inspect "$IMAGE_NAME"
```

`spring-boot:build-image` phù hợp để gọi trực tiếp từ CLI vì nó có thể fork lifecycle tới package, bảo đảm JAR đầu vào. Dù đã chạy `mvn verify` trước đó, goal này có thể làm lại một số bước package; trong CI có thể dùng goal no-fork sau verify.

Với `publish=false`, plugin không cần push vào target private registry. Tuy nhiên, nếu POM/provider của bạn resolve và kiểm tra các publishRegistry values ngay cả khi không publish, bạn có thể cung cấp giá trị thử không nhạy cảm hoặc dùng Maven profile local riêng. Không cung cấp secret thật chỉ để chạy unit test không cần đăng nhập.

### 5.2. Maven publish sau các quality gates

Với `IMAGE_NAME`, `REGISTRY_USER`, `REGISTRY_TOKEN` đã được CI secret store cung cấp:

```bash
test -n "${IMAGE_NAME:-}"
test -n "${REGISTRY_USER:-}"
test -n "${REGISTRY_TOKEN:-}"

mvn -B -ntp verify spring-boot:build-image-no-fork \
  -Dspring-boot.build-image.publish=true
```

**Tại sao dùng `build-image-no-fork` ở đây?** Maven chạy lifecycle `verify` trước, hoàn thành `package` và các goals đã bind, rồi chạy goal CNB **không fork lại lifecycle**. Nó phù hợp khi release policy muốn tránh chạy lại `package` ngoài ý muốn. Với lần gọi CLI đơn độc, dùng `spring-boot:build-image` (có fork) thay vì `build-image-no-fork` trên workspace chưa có JAR.

**Đừng suy rằng Maven `verify` tự chạy mọi static/security/integration checks**: những plugin/job đó phải được cấu hình và đánh dấu required theo policy. Nếu một vulnerability scan bên ngoài Maven là bắt buộc, publish job phải chờ nó pass.

### 5.3. Các thuộc tính CLI thường gặp

| Maven option | Ý nghĩa |
| --- | --- |
| `-Dspring-boot.build-image.imageName=...` | Chọn tên image từ CLI theo plugin property |
| `-Dspring-boot.build-image.publish=true` | Yêu cầu publish |
| `-Dspring-boot.build-image.builder=...` | Override builder image |
| `-Dspring-boot.build-image.runImage=...` | Override run image |
| `-Dspring-boot.build-image.pullPolicy=ALWAYS` | Quy tắc pull builder/run |
| `-B -ntp` | Maven batch mode và giảm progress download output |

Khi POM đã định nghĩa `<name>${env.IMAGE_NAME}</name>`, ưu tiên chỉ **một nguồn cấu hình** từ `IMAGE_NAME` để tránh ambiguity giữa environment và CLI override. Kiểm tra tên thực trong logs mà không làm lộ secret.

## 6. Maven dùng private builder/run images

Nếu builder và run image được mirror vào kho nội bộ, dùng fragment **thay thế** phần `<image>` và `<docker>` ở trong configuration của Spring Boot Maven Plugin:

```xml
<image>
    <name>${env.IMAGE_NAME}</name>
    <builder>${env.CNB_BUILDER_IMAGE}</builder>
    <runImage>${env.CNB_RUN_IMAGE}</runImage>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
    </env>
</image>
<docker>
    <builderRegistry>
        <username>${env.BUILDER_REGISTRY_USER}</username>
        <password>${env.BUILDER_REGISTRY_TOKEN}</password>
    </builderRegistry>
    <publishRegistry>
        <username>${env.REGISTRY_USER}</username>
        <password>${env.REGISTRY_TOKEN}</password>
    </publishRegistry>
</docker>
```

Biến môi trường mong đợi (tên chỉ để mô tả, không chứa secrets thật):

```text
CNB_BUILDER_IMAGE = mirror.corp.example/buildpacks/java-builder:approved
CNB_RUN_IMAGE     = mirror.corp.example/buildpacks/java-run:approved
IMAGE_NAME        = registry.example.com/team/cnb-registry-demo:1.0.0
BUILDER_REGISTRY_USER  = injected-from-ci-secret-store
BUILDER_REGISTRY_TOKEN = injected-from-ci-secret-store
REGISTRY_USER          = injected-from-ci-secret-store
REGISTRY_TOKEN         = injected-from-ci-secret-store
```

**Đây không phải POM hoàn chỉnh và các chuỗi injected-from-ci-secret-store không phải token hợp lệ.** Cần nguồn credentials thật được cấp quyền và image builder/run thực sự tồn tại, tương thích.

**Giới hạn quan trọng:**

- `builderRegistry` điều khiển việc truy cập builder/run image private; `publishRegistry` điều khiển application push.
- Nếu hai private images nằm ở **hai registries riêng** và cần hai identities khác nhau, phải kiểm chứng plugin/daemon/credential helper hỗ trợ đúng từng host. Không mặc định một `builderRegistry` credential pair có thể dùng cho mọi host.
- Docker registry credential không giải quyết private Maven repository, buildpack dependency mirror hay HTTP proxy riêng. Những nguồn đó cần cấu hình/binding và trust riêng.
- Run image phải tương thích stack/lifecycle của builder. Đổi run image để “nhỏ hơn” mà không kiểm tra compatibility có thể gây lỗi launch.
- Builder/run image nên được chọn qua tag/digest đã phê duyệt và có scan/signing policy, không chọn image ngẫu nhiên do registry “đăng nhập được”.

## 7. Gradle 3.3: `bootBuildImage` với publishRegistry

Gradle dùng task `bootBuildImage` của Spring Boot Gradle Plugin. Đây là **alternative build** cho cùng source Java ở mục 4; không cần POM khi chọn Gradle.

`settings.gradle`:

```groovy
rootProject.name = 'cnb-registry-demo'
```

`build.gradle` đầy đủ (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

def imageInput = providers.environmentVariable('IMAGE_NAME')
        .orElse('registry.example.com/team/cnb-registry-demo:local')
def userInput = providers.environmentVariable('REGISTRY_USER')
def tokenInput = providers.environmentVariable('REGISTRY_TOKEN')

tasks.named('bootBuildImage') {
    imageName = imageInput.get()

    docker {
        publishRegistry {
            if (userInput.present && tokenInput.present) {
                username = userInput.get()
                password = tokenInput.get()
            }
        }
    }
}
```

**Ý nghĩa:**

- `bootBuildImage` tạo OCI image từ executable Boot app với CNB; tên image được đặt rõ ràng và có default cho local.
- `publishRegistry` lấy credentials từ environment chỉ khi cả hai biến có mặt. **Release job phải fail sớm** nếu biến thiếu; không tin vào default local credential fallback để publish.
- Không mặc định `publish=true` trong build script. CI bật `--publishImage` có chủ đích.
- Test dùng JUnit Platform. Chạy `bootBuildImage` riêng có thể không chạy tất cả các verification tasks; required CI nên chạy `build` cùng các checks riêng được policy yêu cầu.
- `providers.environmentVariable` đọc variables của Gradle process, không phải secrets lưu bên trong image. Nhưng `get()` khi configuring task có thể ảnh hưởng configuration cache/caching, cần quản lý trên Gradle/plugin version cụ thể; không log resolved token.

### 7.1. Gradle local và CI

Nếu repository có Gradle Wrapper tương thích Spring Boot 3.3:

```bash
./gradlew clean build
./gradlew bootBuildImage
docker image inspect registry.example.com/team/cnb-registry-demo:local
```

Trên Windows dùng `gradlew.bat`. Không giả định mọi repository có wrapper; nếu thiếu thì phải tạo/cài một version Gradle tương thích.

CI sau khi inject secrets và image name:

```bash
test -n "${IMAGE_NAME:-}"
test -n "${REGISTRY_USER:-}"
test -n "${REGISTRY_TOKEN:-}"

./gradlew clean build bootBuildImage --publishImage
```

`./gradlew build` (Java lifecycle) và `bootBuildImage` là hai đầu việc cần phân biệt; `bootBuildImage` không tự chứng minh unit/integration/security gates đạt. CLI `--publishImage` là **task option của bootBuildImage**, không phải Docker daemon setting.

### 7.2. Gradle private builder registry

Thay thế/mở rộng khối task tương ứng khi CI có cả builder/run credentials:

```groovy
tasks.named('bootBuildImage') {
    imageName = providers.environmentVariable('IMAGE_NAME').get()
    builder = providers.environmentVariable('CNB_BUILDER_IMAGE').get()
    runImage = providers.environmentVariable('CNB_RUN_IMAGE').get()

    docker {
        builderRegistry {
            username = providers.environmentVariable('BUILDER_REGISTRY_USER').get()
            password = providers.environmentVariable('BUILDER_REGISTRY_TOKEN').get()
        }
        publishRegistry {
            username = providers.environmentVariable('REGISTRY_USER').get()
            password = providers.environmentVariable('REGISTRY_TOKEN').get()
        }
    }
}
```

Đây là **fragment thay thế khối `tasks.named('bootBuildImage')`**, không phải thêm hai khối publishRegistry cạnh tranh nhau. `Provider.get()` sẽ fail nếu các biến CI chưa cung cấp; đó là hành vi phù hợp với **release configuration bắt buộc**. Khi builder/run public, bỏ cấu hình builderRegistry và không yêu cầu builder secrets.

## 8. Docker login và credential helpers

Docker CLI sử dụng credential store riêng. Cách đăng nhập không để password/token trên command line là:

```bash
test -n "${REGISTRY_USER:-}"
test -n "${REGISTRY_TOKEN:-}"

printf '%s' "$REGISTRY_TOKEN" |
  docker login registry.example.com \
    --username "$REGISTRY_USER" --password-stdin
```

Ở đây token đã được **secret manager** inject vào môi trường; ví dụ không có giá trị thật. `docker login` nhận **registry host** (có thể kèm port), không nhận repository path `registry.example.com/team`.

### 8.1. Credential store là gì?

Docker có thể dùng:

- OS keychain/credential manager từ Docker Desktop.
- Per-registry `credHelpers` hoặc global `credsStore`.
- Docker config file (`$HOME/.docker/config.json` hoặc thư mục `DOCKER_CONFIG`).

Nếu không có helper/store, Docker có thể lưu auth **base64-encoded** trong `config.json`. Base64 **không phải mã hóa bảo mật**; không commit file config, không print config vào logs và không share giữa unrelated CI jobs.

**Spring Boot plugin không phải Docker CLI.** Việc `docker login` thành công trên máy developer không đảm bảo Maven/Gradle plugin trong CI cùng thấy credential helper và config. Spring Boot 3.3 có cấu hình `docker.publishRegistry`/`docker.builderRegistry` tường minh; bài này sử dụng chúng cho plugin. Nếu một plugin/version hỗ trợ đọc Docker config, hãy kiểm chứng hành vi trên CI runner thực tế trước khi bỏ cấu hình explicit.

### 8.2. Token, password và identity token

Spring Boot 3.3 hỗ trợ username/password hoặc `token` theo auth method registry chấp nhận. Một số nhà cung cấp phát **short-lived registry access token** rồi dùng nó như password khi Docker Registry protocol yêu cầu username/password; nơi khác dùng identity token trực tiếp. **Không trộn hai dạng tuỳ tiện**. Cần đọc tài liệu của registry đang sử dụng và cấp quyền đúng scope.

### 8.3. Tách pull và push

- Writer token: chỉ cấp cho trusted publish job, quyền ghi vào một app repository.
- Builder pull token: chỉ đọc builder/run images.
- Deployment pull token: chỉ đọc app image tại production/staging, không cần builder.
- Nếu CI dùng OIDC federation để lấy short-lived token từ cloud registry, ưu tiên hơn secret cố định nếu được hỗ trợ.
- Không nhúng credentials vào JAR, OCI image labels, image name, buildpack env `BP_*`, Dockerfile `ENV` hoặc output logs.

## 9. CI mẫu GitHub Actions để publish lên GHCR

GitHub Container Registry dùng `ghcr.io`. GitHub Actions có thể dùng `GITHUB_TOKEN` với job permission `packages: write` để publish vào package có quyền phù hợp. Điều này còn tùy package-level permissions, org policy và repository association; `packages:write` không đồng nghĩa token đẩy được vào bất kỳ repository nào.

Workflow ví dụ cho **Maven project ở mục 5**, trigger chỉ là push lên main:

`.github/workflows/publish-image.yml`:

```yaml
name: Verify and publish CNB image

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  image:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Define image target from commit
        shell: bash
        run: |
          set -euo pipefail
          image="ghcr.io/${GITHUB_REPOSITORY,,}:${GITHUB_SHA}"
          echo "IMAGE_NAME=$image" >> "$GITHUB_ENV"

      - name: Verify and publish with buildpacks
        shell: bash
        env:
          REGISTRY_USER: ${{ github.actor }}
          REGISTRY_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          test -n "${IMAGE_NAME:-}"
          test -n "${REGISTRY_USER:-}"
          test -n "${REGISTRY_TOKEN:-}"
          mvn -B -ntp verify spring-boot:build-image-no-fork \
            -Dspring-boot.build-image.publish=true

      - name: Verify private image is pullable
        shell: bash
        env:
          REGISTRY_USER: ${{ github.actor }}
          REGISTRY_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          printf '%s' "$REGISTRY_TOKEN" |
            docker login ghcr.io \
              --username "$REGISTRY_USER" --password-stdin
          docker pull "$IMAGE_NAME"
          docker image inspect --format '{{json .RepoDigests}}' "$IMAGE_NAME"
          docker logout ghcr.io
```

**Điểm kỹ thuật cần đọc:**

1. `GITHUB_REPOSITORY` có dạng `owner/repo`; cú pháp Bash `${GITHUB_REPOSITORY,,}` chuyển lowercase để hợp lệ với OCI repository naming. `GITHUB_SHA` là event revision trong workflow push; nếu chuyển sang PR, cần tách PR head và checkout merge SHA.
2. `GITHUB_ENV` đặt env cho các **bước sau**, không được coi như output của cùng một script ngay lập tức. Build step sau đó nhận `IMAGE_NAME`.
3. `GITHUB_TOKEN` là token do Actions cấp, chỉ xuất hiện trong env của trusted steps; không lưu vào source/POM.
4. Plugin Maven dùng `${env.REGISTRY_USER}`/`${env.REGISTRY_TOKEN}` từ POM, không cần Docker CLI login trước để publish. Step cuối dùng **Docker CLI login riêng** để pull image và đọc remote digest.
5. `mvn verify spring-boot:build-image-no-fork` chạy phase verification/package đã được bind trước rồi mới build/publish image; nếu CI có static/SBOM/security checks ở jobs khác, cần required status/dependency trước publish.
6. `packages: write` phải thực sự được organization/repository/package chấp nhận. Nếu GHCR trả `denied`, kiểm tra package access và repo linkage trước khi xin quyền rộng hơn.
7. `docker pull` sau publish chứng minh remote registry có image và account hiện tại đọc được; `RepoDigests` phải được ghi đúng reference/digest vào release record. Workflow rút gọn chỉ **in digest để quan sát**; release pipeline thật cần trích xuất, kiểm tra và lưu digest có cấu trúc.
8. Major action tags như `@v4` là minh họa; CI production nên pin **immutable action commit SHA** đã kiểm duyệt và thực hiện supply-chain hardening.

### 9.1. Vì sao không publish từ untrusted Pull Request?

Một PR từ fork có thể sửa Maven/Gradle build scripts. Nếu job chạy code đó với write token, tác giả PR có thể gây lộ credentials hoặc đẩy image độc hại. Test PR trong job không có publish secret; release chỉ khi merge protected branch/tag và required checks pass. Không sử dụng `pull_request_target` để checkout untrusted PR code với secrets mà không có isolation/review đặc biệt.

## 10. Xác minh image đã được publish và lấy manifest digest

**Đừng chỉ dựa vào log “BUILD SUCCESS” hoặc `docker images`.** Hai điều đó có thể chỉ nói local build thành công. Sau publish, dùng read identity riêng để truy vấn **remote registry**.

Linux/macOS Bash:

```bash
IMAGE_NAME="registry.example.com/team/cnb-registry-demo:1.0.0"

docker pull "$IMAGE_NAME"
docker image inspect --format '{{json .RepoDigests}}' "$IMAGE_NAME"
```

Sau khi pull, `RepoDigests` có thể chứa:

```text
["registry.example.com/team/cnb-registry-demo@sha256:..."]
```

Dấu `...` là **minh họa**, không có digest thật. Cần chọn đúng repository và lưu đầy đủ digest. Một image local có thể có nhiều RepoDigests do pull/tag qua nhiều repository.

| Định danh | Nói về điều gì? | Có dùng để pin deployment không? |
| --- | --- | --- |
| Image tag | Human-readable pointer, có thể bị overwrite | Không đủ nếu thiếu immutability |
| Local image ID | Digest của image config trong Docker daemon | Không mặc định bằng manifest digest |
| OCI registry manifest digest | Manifest hoặc multi-platform index do registry lưu | Có, cùng full repository reference |
| Layer digest | Một layer riêng | Không thay whole-image identity |
| Git commit SHA | Revision source | Không tự bằng image digest |

Không nhầm `docker image inspect ... Id` với `RepoDigests`. **Image ID và registry manifest digest không luôn cùng đối tượng**, vì image config, manifest và index là các nội dung khác nhau.

### 10.1. Khi pin image theo digest

Format:

```text
registry.example.com/team/cnb-registry-demo@sha256:<FULL_MANIFEST_DIGEST>
```

Đây chỉ là cú pháp mẫu. CI phải lấy `FULL_MANIFEST_DIGEST` từ registry. Sau đó deployment dùng exact reference để tránh tag drift. Với multi-platform images, phân biệt digest **OCI index** và từng platform manifest; chọn digest phù hợp release/cluster policy.

### 10.2. Remote pull khác quyền push

CI có thể push bằng token writer nhưng Kubernetes Pod vẫn `ImagePullBackOff` do thiếu pull identity, expired token, sai namespace, TLS/CA hoặc platform. Spring Boot `publishRegistry` **không** đi theo image sang production. Cluster cần Kubernetes `imagePullSecrets`/workload identity có quyền read riêng.

## 11. Smoke test chính image sau khi pull

Sau khi có `IMAGE_NAME` thực và đã `docker pull` thành công:

```bash
docker image inspect --format '{{.Config.User}}' "$IMAGE_NAME"
docker image inspect --format '{{.Config.Entrypoint}}' "$IMAGE_NAME"

docker run --rm --name cnb-registry-demo-test \
  -p 127.0.0.1:18080:8080 \
  "$IMAGE_NAME"
```

Đợi log Spring Boot startup; mở **terminal thứ hai**:

```bash
curl -fsS http://127.0.0.1:18080/status
```

Body dự kiến:

```text
cnb-ready
```

Ví dụ dùng loopback port mapping, không tự mở ra toàn mạng LAN. CNB builder/runtime stack có launcher và runtime user riêng; **không mặc định rằng entrypoint luôn là `java -jar` hoặc UID là `10001`** như khi tự viết Dockerfile.

Trong CI, dùng process management, timeout, log capture, cleanup để test không treo vô hạn. Kết quả smoke test chứng minh image HTTP hoạt động trên môi trường thử, **không chứng minh production database/network đã sẵn sàng**.

## 12. Registry và quyền truy cập theo nhà cung cấp

| Registry | Image name thường gặp | Auth strategy phổ biến | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Docker Hub | `docker.io/org/app:1.0` | Username + access token | Org/repository ACL, rate limit |
| GitHub Container Registry | `ghcr.io/org/app:sha` | `GITHUB_TOKEN` hoặc PAT phù hợp | `packages:write`, package/repo association |
| GitLab Registry | `registry.gitlab.com/group/project/app:sha` | Job/deploy token hoặc user/token | Scope của project và token |
| Amazon ECR | `account.dkr.ecr.region.amazonaws.com/app:sha` | IAM lấy short-lived Docker login password | Account/region/repository IAM |
| Google Artifact Registry | `region-docker.pkg.dev/project/repository/app:sha` | Workload identity/service account | Project/location/IAM |
| Azure Container Registry | `myregistry.azurecr.io/app:sha` | Managed identity, service principal/token | AcrPush/AcrPull |
| Harbor/self-hosted | `harbor.example.com/team/app:sha` | Robot account/token | Project RBAC, CA, tag immutability |

Đây là **cấu trúc minh họa**. Registry credentials được Spring Boot plugin tiêu thụ dưới dạng Docker Registry auth mà nhà cung cấp chấp nhận; ví dụ AWS access key trực tiếp **không** mặc định là password cho ECR. Trước tiên cloud IAM cấp/quy đổi token registry hợp lệ, sau đó truyền vào plugin/CLI.

### 12.1. Không dùng token có quyền cao cho mọi bước

CI publisher cần push vào **đúng repository**, không cần quyền quản lý tất cả org packages. Builder mirror chỉ cần pull. Kubernetes chỉ cần pull. Nếu policy hỗ trợ token OIDC/ngắn hạn, ưu tiên tránh PAT dài hạn. Không bao giờ commit token vào POM, build.gradle, Dockerfile hoặc `.github/workflows`.

## 13. TLS, CA và network: lỗi khác hoàn toàn auth

Các vấn đề thường bị nhầm là “mật khẩu sai”:

| Lỗi | Tầng | Cách điều tra |
| --- | --- | --- |
| `Cannot connect to Docker daemon` | Daemon/socket | `docker info`, Docker context, `DOCKER_HOST` |
| `401 Unauthorized` | Registry authentication | Username/token/expiry/method |
| `403 Forbidden` hoặc `denied: requested access to resource is denied` | Registry authorization | Scope write, namespace, package permissions |
| `x509: certificate signed by unknown authority` | TLS/CA trust | Cài CA hợp lệ, hostname, certificate chain |
| `dial tcp ... timeout` | DNS/firewall/proxy | Đường mạng runner/daemon/builder |
| `manifest unknown` | Reference | Đúng host/repo/tag/digest, push đã hoàn tất? |
| `ImagePullBackOff` | Deployment runtime | imagePullSecret, ServiceAccount, CA, platform |
| `no basic auth credentials` | Auth lookup | Plugin credentials, Docker config/DOCKER_CONFIG |

Kiểm tra daemon:

```bash
docker version
docker info
docker context ls
```

Nếu Docker host dùng TLS/remote daemon, phải cấu hình đúng client certificate/`docker.host`/`tlsVerify`/`certPath` theo Spring Boot plugin documentation. **`docker.host` là Docker daemon endpoint, không phải `publishRegistry.url`**. Không expose Docker TCP API không TLS/auth hoặc chạy privileged container chỉ để chữa lỗi permission.

### 13.1. Builder container có network riêng

CNB builder có thể cần tải JDK/buildpack dependencies, Maven dependencies hoặc SBOM metadata từ nơi khác. Credentials cho OCI registry **không tự** mở private Maven repository hoặc HTTP proxy. Khi thấy timeout, xác định **hostname bị lỗi**; không thay token push trước khi biết request thuộc tầng nào.

### 13.2. Private CA

Nếu self-hosted registry có CA nội bộ, Docker daemon/runtime và thành phần builder cần trust CA phù hợp. Không bật `insecure-registries`/bỏ TLS trên production một cách phản xạ. Nếu private network/firewall chặn, phải điều chỉnh policy mạng thay vì vô hiệu hóa xác thực.

## 14. An toàn secrets trong quy trình build và publish

### 14.1. Cách không nên dùng

```bash
# Sai: password có thể xuất hiện trong command line/history
docker login registry.example.com -u real-user -p plain-text-password

# Sai: secret có thể lộ qua process list hoặc CI log
mvn spring-boot:build-image -Ddocker.publishRegistry.password=plain-text-password
```

Không viết `password = "plain-text-password"` cố định trong Gradle script; không đặt PAT vào `BP_*` env; không cho image labels/tags chứa auth data; không commit `~/.docker/config.json`.

### 14.2. Cách nên làm

1. Dùng CI secret manager hoặc cloud workload identity.
2. Chỉ inject secrets vào trusted release job sau required checks.
3. Token scope chỉ read/pull builder, write/push đúng app repository; không cấp admin mặc định.
4. Thích token ngắn hạn, có rotation, revocation và audit log.
5. Dùng `docker login --password-stdin` nếu chọn Docker CLI push.
6. Với plugin, dùng `publishRegistry`/`builderRegistry`, tránh CLI `-D...password` dễ lộ.
7. Không in biến môi trường và resolved build config khi chứa secrets.
8. Không cho untrusted PR/fork code chạy với publisher token.
9. Không chia sẻ Docker credential store giữa nhiều CI tenants.
10. Lưu builder/run image digests, source commit, registry manifest digest để hỗ trợ provenance và incident response.

**Quan trọng:** Secret ở environment vẫn có thể lộ trong process dumps, CI debug logging hoặc malicious build scripts. Sự bảo vệ thực sự phụ thuộc trust boundary của runner, permission, masking và vòng đời token.

## 15. CI multi-module và chọn đúng image phát hành

Với Maven monorepo:

```text
platform-parent/             root POM
├── common-library/          plain JAR
└── api-service/             Boot executable app + CNB image
```

Chỉ app cần Spring Boot image plugin/publish configuration. Với reactor, có thể test selected upstream modules:

```bash
mvn -B -ntp -pl :api-service -am verify
```

Sau đó build-image cho app từ artifact có sẵn, tùy chọn reactor/dependency artifact resolution và exact Maven lifecycle. **Đừng giả định** `mvn -pl :api-service spring-boot:build-image` luôn lấy source mới của sibling library nếu core chưa được publish/install; phải bảo đảm dependency đúng version.

Gradle multi-project:

```bash
./gradlew :api-service:build :api-service:bootBuildImage --publishImage
```

Đây là **fragment cho repository có module api-service** và plugin được áp dụng ở module đó. Gradle chạy task dependencies từ upstream modules khi cần, nhưng không tự test mọi sibling/downstream modules nếu không được chọn. Release policy phải quy định required tests cho phạm vi thay đổi.

Với nhiều image cùng CI run, ghi **digest riêng** cho từng module/application. Run ID không thay thế artifact identity, và hai jobs không nên cùng ghi một mutable tag mà không phối hợp.

## 16. Chuỗi truy vết từ commit đến image digest

Một release record hữu ích gồm:

```text
source.repository = org/service-repository
source.commit     = full Git SHA from checked-out HEAD
ci.run.id         = provider run identifier
ci.run.attempt    = retry/attempt number
module            = api-service
image.reference   = registry.example.com/team/api-service:version-or-sha
image.digest      = sha256 value read from registry manifest
builder.digest    = approved CNB builder digest
run.image.digest  = approved run image digest
validation        = required tests, scan and smoke-test result
```

Đây là **sơ đồ dữ liệu**, không phải kết quả CI đã chạy. **Tính chính xác phải dựa trên bằng chứng thực tế**:

1. Git checkout có full commit SHA.
2. Maven/Gradle tests và static/security checks bắt buộc pass.
3. CNB build sử dụng builder/run images được kiểm soát.
4. Publish thực sự gửi application image tới tên repository đã định.
5. Pull lại image từ registry và lấy verified manifest digest.
6. Smoke test container dựa trên remote image/digest.
7. Deployment lấy **chính digest đã qua QA**, không rebuild khi deploy.
8. Có thể lưu OCI SBOM và signed provenance/attestation subject digest nếu policy yêu cầu.

Image tag/label chứa Git SHA là dữ liệu tự khai báo, không phải chữ ký chứng minh supply chain. Khi cần tính xác thực, CI builder ký attestation và deployment verify builder identity + subject digest.

### 16.1. Image ID không phải manifest digest

Docker local image `Id` thường gắn với image config digest. Registry reference theo `@sha256:...` cần manifest/index digest được registry cung cấp. Không thay bằng local image ID khi ghi Kubernetes deployment.

### 16.2. Vì sao cùng commit vẫn có nhiều digest?

Builder/run images có thể đổi qua mutable tags, buildpack dependencies thay đổi, môi trường build khác, timestamps/build metadata thay đổi hoặc CI run-specific values bị nhúng. Để reproducible build, pin inputs và builder/run digests, quản lý timestamps và kiểm thử repeatability thực tế. Dùng một commit SHA không đủ khẳng định byte image giống nhau.

## 17. Chẩn đoán lỗi thường gặp

| Hiện tượng | Khả năng cao | Hướng xử lý |
| --- | --- | --- |
| Build local success, không thấy image trên registry | Publish đang false | Bật `-Dspring-boot.build-image.publish=true` hoặc `--publishImage` trong trusted job |
| Image lên Docker Hub, không phải private registry | Image name không có host private | Đặt full image name `registry.example.com/team/app:tag` |
| Push `401 Unauthorized` | Credentials sai/hết hạn | Xác nhận username/token type/expiry; không log token |
| Push `403 Forbidden` | Thiếu write scope | Kiểm tra repo/namespace/package ACL, tránh tăng quyền toàn cục |
| Private builder pull fail | Không có `builderRegistry` đúng host | Tách auth pull builder/run với push app |
| Builder pull được, publish fail | Builder token read-only | Cấp riêng publish token write |
| GHCR denied dù có `packages:write` | Package access/association chưa phù hợp | Kiểm tra org/package/repo policy |
| Docker CLI push fail còn Maven plugin publish pass | Docker CLI credentials khác plugin | Docker login --password-stdin/credential helper cho CLI |
| CI pass trên laptop nhưng fail runner sạch | Local Docker config/cache giúp developer | Cấu hình auth explicit trên CI |
| `x509 unknown authority` | Private CA | Sửa trust store/CA/TLS; không tắt TLS |
| Docker daemon unavailable | Socket/context/TLS | `docker info`, Docker context, socket rights |
| Registry `manifest unknown` khi pull | Sai repo/tag, publish khác host hoặc chưa xong | So sánh image name và registry |
| Kubernetes `ImagePullBackOff` | Thiếu deployment read identity | ImagePullSecret/ServiceAccount, node CA, reference |
| Image push được nhưng container không start | Run image/JDK/launcher/app config | Docker logs, stack/run compatibility, smoke test |
| ECR token hết hạn | Cloud registry credential ngắn hạn | Tạo token gần thời điểm push |
| Immutable tag push bị từ chối | Tag đã có | Sinh tag mới đúng chính sách; không vô hiệu immutability |
| Image multi-platform từ job khác cùng tag | Tag race | Tag riêng từng job/platform hoặc assemble OCI index có điều phối |
| Docker registry push token có mặt trong logs | Build verbose/command line chứa secret | Thu hồi và rotate token, xử lý log theo security policy |

### Checklist điều tra nhanh

1. Tên image đã chứa **đúng registry host + repo + tag** chưa?
2. Plugin `publish` đã bật chưa? Docker daemon có chạy không?
3. Lỗi ở **builder pull**, **run image pull**, **app push** hay **runtime pull**?
4. Credentials có tồn tại trong trusted job và đúng **scope** không (chỉ kiểm tra presence, không in value)?
5. Registry hiện trả 401, 403, TLS hay network error?
6. Builder/run image versions và stack compatibility có đúng không?
7. Image đã có remote manifest digest chưa? Có thể pull lại không?
8. Đã chạy smoke test từ published image và lưu digest vào release record chưa?

## 18. Bài tập tự kiểm tra

**Bài A.** POM có `docker.publishRegistry.url=registry.example.com` nhưng `image.name=docker.io/library/app:1.0`. Image sẽ publish vào đâu?

*Đáp án:* Đích lấy từ image name. Cần sửa name thành `registry.example.com/team/app:1.0`; URL credentials không tự chuyển host.

**Bài B.** CNB builder image trong private registry trả `401`, nhưng app writer token vẫn hợp lệ. Xem cấu hình nào?

*Đáp án:* `docker.builderRegistry` credentials và host của builder/run image; không chỉ `publishRegistry`.

**Bài C.** Gradle `bootBuildImage` build xong, `docker images` nhìn thấy artifact. Có thể deploy production từ private registry chưa?

*Đáp án:* Chưa chứng minh. Phải bật publish, xác nhận push, pull image từ registry và lấy digest.

**Bài D.** CI có push token và copy nó sang Kubernetes imagePullSecret. Có phù hợp least privilege?

*Đáp án:* Không. Pod chỉ cần read/pull scope; push token không nên nằm ở runtime.

**Bài E.** Job GHCR có `packages:write` nhưng bị `denied`. Có chắc Spring Boot plugin lỗi?

*Đáp án:* Không. Kiểm tra GitHub package access, repository linkage, org settings và permission thực của token.

**Bài F.** Docker `Image ID` khác `RepoDigests`. Dùng giá trị nào pin ở deployment?

*Đáp án:* Dùng registry repository reference với verified **manifest/index digest**, không tự thay bằng local config image ID.

**Bài G.** Developer đã `docker login` nhưng CI Maven plugin không thấy token. Có mâu thuẫn?

*Đáp án:* Không. Môi trường CI khác developer; plugin cần auth settings/credential helpers ở đúng runner. Tài liệu có cấu hình `publishRegistry` tường minh.

**Bài H.** CI publish thành công nhưng Kubernetes `ImagePullBackOff`. Maven publishRegistry có vấn đề không?

*Đáp án:* Chưa chắc. Runtime pull là bước khác, kiểm tra Pod identity/imagePullSecret, network/TLS, image ref và platform.

**Bài I.** Dùng biến `BP_JVM_VERSION` để chứa access token cho private Maven repo hoặc OCI registry có đúng không?

*Đáp án:* Không. Đây là buildpack setting chọn Java version; secret phải qua auth/bindings thích hợp, không đưa vào builder environment chung.

**Bài J.** Dùng tag chứa Git SHA có đảm bảo rollback đúng byte image không?

*Đáp án:* Không nếu tag mutable. Lưu digest đã qua QA và deploy/rollback theo digest.

## 19. Checklist trước khi xuất bản image private

**Chuẩn bị:**

- Spring Boot app có main class, Java 17 toolchain và required tests.
- Docker-compatible daemon chạy được, CNB builder/run stack phù hợp.
- Full image name có registry host, repository namespace và tag đúng quy tắc.
- Builder/run private registry credentials là read-only; publishRegistry là writer hẹp.
- Token ngắn hạn được secret manager inject, không nằm trong source/POM literal/build logs.
- Runner có network/DNS/TLS/CA đúng tới builder/run/app registry.

**Build và publish:**

- Maven `build-image` hoặc Gradle `bootBuildImage` được gọi ở đúng module app.
- Required unit/IT/static/security checks thực sự pass trước publish theo policy.
- Publish option được bật **chủ động trong trusted job**, không trên untrusted PR.
- Registry đích lấy từ image name, không nhầm `publishRegistry.url`.
- Plugin dùng đúng auth scheme/token, builder image và run image hợp lệ.
- Build/push lỗi phải làm CI fail, không dùng `|| true` hay `ignoreFailures`.

**Xác minh và triển khai:**

- Image remote có thể pull được bằng read identity khác token push.
- Registry manifest digest được ghi cùng Git SHA, CI run/attempt và module.
- Smoke test thực hiện trên image đã pull, không chỉ chạy JAR local.
- Deployment dùng verified digest, có riêng pull identity/imagePullSecrets.
- SBOM/vulnerability scan, signing/attestations và immutable tags theo chính sách.
- Không rebuild image ở deploy stage rồi giữ nguyên tag/version của artifact cũ.

**Kết luận:** Với CNB, **registry auth và image publication là hai trách nhiệm phải cấu hình riêng cho từng hướng dữ liệu**: đọc builder/run images qua `builderRegistry`, ghi application image qua `publishRegistry`. **Full image name** chọn đích push; **publish option** cho phép gửi image; **CI secrets/permissions** quyết định quyền; **remote digest + smoke test** xác nhận sản phẩm đã thực sự tồn tại và dùng được. “Local image build thành công” chỉ là bước đầu, không phải bằng chứng đã xuất bản an toàn.

### Tài liệu chính thức

- Spring Boot 3.3 — Maven Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html
- Spring Boot 3.3 — Gradle Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html
- Spring Boot 3.3 — Maven build-image-no-fork: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image-no-fork.html
- Spring Boot 3.3 — Maven Plugin Goals: https://docs.spring.io/spring-boot/3.3/maven-plugin/goals.html
- Docker CLI — docker login: https://docs.docker.com/reference/cli/docker/login/
- Docker CLI — docker image push: https://docs.docker.com/reference/cli/docker/image/push/
- Docker CLI — docker image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Cloud Native Buildpacks Documentation: https://buildpacks.io/docs/
- GitHub Docs — Package publishing via Actions: https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions
- GitHub Docs — Container Registry: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- Kubernetes — Pull an Image from a Private Registry: https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/