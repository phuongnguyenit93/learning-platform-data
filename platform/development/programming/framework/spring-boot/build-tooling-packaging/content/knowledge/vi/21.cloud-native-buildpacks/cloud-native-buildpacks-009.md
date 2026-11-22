# Phân biệt biến môi trường lúc build image với biến môi trường lúc chạy

## Mục tiêu bài học

**Cloud Native Buildpacks (CNB)** giúp đóng gói ứng dụng Spring Boot thành OCI image mà không cần tự viết Dockerfile. Người dùng vẫn cần cấu hình build và runtime, nhưng một lỗi rất thường gặp là sử dụng **biến môi trường được cấp lúc build image** như thể nó sẽ tự xuất hiện ở **container khi chạy**.

Hãy xem bốn ví dụ khác nhau:

- `BP_JVM_VERSION=17`: Paketo Java Buildpack đọc giá trị này **khi tạo image** để chọn Java runtime cần đưa vào image.
- `SPRING_PROFILES_ACTIVE=staging`: Spring Boot đọc ở **runtime**, khi process ứng dụng khởi động trong một container.
- `BPL_JVM_THREAD_COUNT=100`: Paketo launch component, nếu có, đọc ở **runtime** để điều chỉnh giả định cho JVM memory calculator; nó không sửa Java source.
- `BPE_DEFAULT_APP_LABEL=from-image`: được đưa vào **lúc build** để Paketo Environment Variables buildpack cố ý **nhúng một mặc định launch** vào image. Đây là ngoại lệ có thiết kế, không phải mọi build-time env đều tự được lưu như vậy.

Vì các biến đều có dạng `NAME=value`, người học dễ nhầm `bootBuildImage.environment`, `spring-boot:build-image` `image.env` và `pack build --env` với `docker run -e`, Docker Compose `environment` hoặc Kubernetes Pod `env`. Chúng **không tương đương**.

Sau bài này, bạn có thể:

1. Phân biệt **host/CI job**, **CNB builder**, **OCI image launch environment**, **container runtime** và **Spring Environment**.
2. Hiểu các nhóm biến **`BP_*`, `BPL_*`, `BPE_*`**, JVM `JAVA_TOOL_OPTIONS` và Spring `SPRING_PROFILES_ACTIVE`, `SERVER_PORT`, `APP_LABEL`.
3. Cấu hình build-time env đúng trong **Gradle `bootBuildImage`**, **Maven `spring-boot:build-image`** và **`pack build --env`**.
4. Viết ứng dụng Spring Boot Java 17+ có HTTP endpoint kiểm tra giá trị environment một cách an toàn.
5. Dùng **cùng một image ID/digest** chạy nhiều container có runtime config khác nhau mà không rebuild image.
6. Biết lúc nào thực sự phải build lại (Java version, buildpack, native compilation, image-embedded defaults) và lúc nào chỉ cần tạo Pod/container mới (profile, DB URL, feature flags).
7. Kiểm chứng kết quả bằng build log, image identity, HTTP response, JVM/runtime diagnostics mà không lộ secret.
8. Thiết kế quy trình CI/CD: **build một lần, scan/test rồi promote cùng image digest**, để config phụ thuộc môi trường được cấp ở thời điểm deploy.

**Bối cảnh ví dụ:** Spring Boot **3.3.13**, Java **17**, Gradle **8.x** hoặc Maven tương thích, Docker/OCI và **Paketo Java Buildpack**. Các tiền tố `BP_`, `BPL_` và `BPE_` là **quy ước của Paketo**, không phải tên biến được mọi CNB builder hỗ trợ. Các ví dụ có điều kiện rõ ràng: cần Docker daemon, builder tương thích, network và đúng phiên bản plugin. Không báo output đã được chạy nếu chỉ là ví dụ dự đoán.

---

## 1. Một pipeline nhưng nhiều không gian environment

### 1.1 Sơ đồ build → image → launch

```text
                Source code, pom.xml/build.gradle
                           |
                        Host / CI
             JAVA_HOME, DOCKER_HOST, CI_*
                           |
                       Maven/Gradle
                     or pack build CLI
                           |
                           v
                Cloud Native Buildpacks
               detect -> build -> export
            BP_JVM_VERSION=17  (BUILD)
                           |
                           v
                      OCI IMAGE
              Java runtime + app classes
           launch process + layers + metadata
           BPE_* có thể nhúng launch default
                           |
             +-------------+--------------+
             |                            |
             v                            v
     Container staging              Container production
     cùng image digest              cùng image digest
     profile=staging                profile=prod
     APP_LABEL=blue                 APP_LABEL=green
     BPL_THREAD_COUNT=50            BPL_THREAD_COUNT=100
             |                            |
             +-------------+--------------+
                           |
                           v
            CNB launcher / runtime components
                           |
                           v
                 Spring Boot process
                        /probe
```

**Image** chứa những filesystem layers, process type, launch env/config do buildpacks tạo và các runtime libraries. **Container** là một lần chạy image đó, có network/mounts/permissions/environment riêng. Việc tạo hai container với environment khác nhau **không làm image thay đổi**.

### 1.2 Bốn vùng cấu hình

| Vùng | Ai đọc? | Ví dụ cách cấp biến | Có tự chuyển sang vùng tiếp theo? |
| --- | --- | --- | --- |
| **Host shell/CI job** | Gradle, Maven, pack CLI, Docker client | Bash `export X=...`; PowerShell `$env:X=...`; CI job env | **Không tự động** truyền mọi biến sang builder hay runtime |
| **Buildpack environment** | CNB lifecycle và các buildpacks | Gradle `bootBuildImage.environment`, Maven `image.env`, `pack build --env` | **Không tự động** biến thành container runtime env |
| **Image-embedded launch environment** | CNB launcher/profile scripts | Paketo `BPE_DEFAULT_*`/`BPE_APPEND_*`; launch layer env | **Có chủ đích** được áp dụng khi image chạy |
| **Container runtime environment** | CNB launch components, JVM, Spring Boot | Docker `-e`, Compose service `environment`, Kubernetes `env` | Có trong **process/container đó**, không sửa image |

Khi bạn thấy một biến xuất hiện trong log builder, hãy hỏi: nó được **truyền đến builder**, **được biến thành artifact**, hay **được lưu làm launch env**? Ba khả năng này khác nhau.

### 1.3 Biến có thể ảnh hưởng byte image mà không được lưu nguyên văn

`BP_JVM_VERSION=17` có thể khiến image chứa Java 17 runtime. Khi container chạy, Java vẫn là 17 ngay cả khi bạn không thấy biến `BP_JVM_VERSION` trong `docker image inspect .Config.Env`. **Hệ quả build** đã được đóng gói; **bản thân biến** không nhất thiết tồn tại trong launch environment.

Ngược lại, `BPE_DEFAULT_APP_LABEL=from-image` là yêu cầu buildpack cố ý tạo **mặc định cho launch**; nó có thể tiếp tục ảnh hưởng container. Còn `SPRING_PROFILES_ACTIVE=prod` được cấp lúc container startup chỉ làm thay đổi runtime configuration, không compile lại lớp Java.

### 1.4 Host env không phải image env

Trong Bash:

```bash
export SPRING_PROFILES_ACTIVE=staging
./gradlew bootBuildImage
```

Lệnh trên đặt một biến trong môi trường **process Gradle ở host**. Không được kết luận rằng CNB builder nhận biến đó, hoặc image được tạo sẽ chạy Spring profile staging. Biến host chỉ được chuyển vào builder nếu một cơ chế build/tool thực sự truyền nó, và được chuyển vào runtime nếu Docker/orchestrator hoặc image launch metadata thực sự cấp nó.

Với Maven cũng tương tự. `-Dspring.profiles.active=staging` dùng cho Maven JVM hoặc một execution/plugin không đồng nghĩa với `SPRING_PROFILES_ACTIVE` của application ở production. Nếu quá trình build chạy integration tests, profile có thể ảnh hưởng **test JVM**, nhưng đó vẫn không phải launch environment của container sản phẩm.

## 2. Quy ước build-time `BP_*` của Paketo

### 2.1 `BP_JVM_VERSION`

`BP_JVM_VERSION` được Paketo Java buildpacks hỗ trợ để chọn Java version được cài khi **tạo image**:

```text
BP_JVM_VERSION=17
```

Một builder có thể cài JDK ở build phase và đóng JRE/runtime phù hợp vào launch image. Spring Boot Maven/Gradle image plugins thường suy ra Java compatibility của project và chỉ dẫn cho builder, nhưng cấu hình `BP_JVM_VERSION` cho phép override theo contract Paketo.

**Cách dùng đúng:**

```bash
pack build example/cnb-env-demo:0.0.1 \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env BP_JVM_VERSION=17
```

Đây là lệnh ví dụ khi executable JAR đã được Gradle tạo, builder có Paketo Java buildpacks và Docker daemon hoạt động. Nếu builder không hỗ trợ Java 17 hoặc tag đã thay đổi, phải chọn builder tương thích thực tế.

**Cách dùng sai nếu muốn nâng Java sau khi build:**

```bash
docker run --rm \
  -e BP_JVM_VERSION=21 \
  example/cnb-env-demo:0.0.1
```

Đây chỉ tạo container với thêm một **runtime environment variable**; nó **không tải, cài hoặc thay Java runtime** đã đóng trong OCI layers. Muốn đổi Java version trong image, tạo image mới bằng build-time option tương ứng rồi kiểm tra tương thích bytecode và behavior.

### 2.2 Một số `BP_*` thường gặp

| Biến | Công dụng Paketo | Khi nào dùng? |
| --- | --- | --- |
| `BP_JVM_VERSION` | Chọn Java version | Trong quá trình build image |
| `BP_JVM_TYPE` | Chọn JDK hoặc JRE launch runtime theo khả năng provider | Trong build image |
| `BP_JVM_JLINK_ENABLED` | Yêu cầu custom runtime `jlink` nếu được hỗ trợ | Trong build image |
| `BP_NATIVE_IMAGE` | Chọn luồng native-image nếu buildpack/builder hỗ trợ | Trong build image |
| `BP_MAVEN_BUILD_ARGUMENTS` | Đổi arguments của Paketo Maven buildpack **khi nó build từ source** | Builder nhận source, không phải đã có executable JAR |
| `BP_GRADLE_BUILD_ARGUMENTS` | Đổi arguments của Paketo Gradle buildpack **khi nó build từ source** | Builder nhận source, không phải đã có executable JAR |
| `MAVEN_OPTS` | JVM options cho Maven process chạy trong builder | Builder build Java source |
| `HTTP_PROXY`/`HTTPS_PROXY` | Proxy mạng khi builder tải dependencies/runtime | Builder/network, cần kiểm tra riêng lúc launch |

**Phân biệt rất quan trọng:** `spring-boot:build-image` và `bootBuildImage` của Spring Boot plugin tạo/đưa **executable archive** vào CNB builder. Các biến build arguments của Paketo Maven/Gradle buildpacks không nhất thiết có tác dụng trong luồng này vì builder có thể chỉ nhận JAR/WAR, không chạy Maven/Gradle bên trong. Khi dùng `pack build --path .` với **source directory** và builder hỗ trợ Java source buildpacks, các biến `BP_MAVEN_BUILD_ARGUMENTS`/`BP_GRADLE_BUILD_ARGUMENTS` mới tác động tới tooling tương ứng.

### 2.3 `BP_*` không phải universal CNB standard

CNB specification định nghĩa lifecycle/buildpack/launch model, nhưng **tên biến config của buildpack** tùy vendor. `BP_JVM_VERSION` là contract phổ biến của Paketo; builder khác có thể dùng tên khác hoặc bỏ qua nó. Không mặc định một `--env BP_FOO=bar` có hiệu lực nếu không có buildpack nhận `BP_FOO`.

Chọn builder theo đúng ứng dụng, stack/run-image compatibility, Java requirements và chính sách cập nhật. Khi thay builder, cần review toàn bộ tên biến config đã dùng.

## 3. Quy ước runtime `BPL_*`

### 3.1 Memory calculator của Paketo

Paketo Java runtime components có thể nhận biến `BPL_*` lúc launch, ví dụ:

- `BPL_JVM_HEAD_ROOM`: điều chỉnh phần memory dự trữ.
- `BPL_JVM_THREAD_COUNT`: giả định số JVM threads cho phép tính stack memory.
- `BPL_JVM_LOADED_CLASS_COUNT`: giả định số class được load.
- `BPL_JVM_CLASS_ADJUSTMENT`: điều chỉnh class estimate nếu component hỗ trợ.

Ví dụ container:

```bash
docker run --rm -d \
  --name cnb-memory-lab \
  --memory 512m \
  -p 18082:8080 \
  -e BPL_JVM_THREAD_COUNT=100 \
  example/cnb-env-demo:0.0.1
```

Nếu Paketo launcher kèm Memory Calculator có mặt, `BPL_JVM_THREAD_COUNT` được đọc trong quá trình **khởi động runtime** để tính `JAVA_TOOL_OPTIONS` hoặc JVM flags. Nó **không** làm thay đổi Java classes trong JAR, không tự sửa config Tomcat thread pool và không phải công cụ để nâng Java 17 thành 21.

Không đưa ra một giá trị heap chính xác khi chưa đo; kết quả còn phụ thuộc cgroup memory limit, Metaspace, thread stacks, native buffers, Java version và memory calculator version. Một số runtime options không hoạt động nếu image dùng buildpacks khác hoặc launcher bị bypass.

### 3.2 `JAVA_TOOL_OPTIONS`

`JAVA_TOOL_OPTIONS` là biến mà JVM có thể đọc khi khởi động; Paketo runtime có thể đóng góp/ghép JVM flags qua biến này. Ví dụ:

```bash
docker run --rm -d \
  --name cnb-timezone-lab \
  -p 18083:8080 \
  -e JAVA_TOOL_OPTIONS="-Duser.timezone=UTC" \
  example/cnb-env-demo:0.0.1
```

Trong image Paketo, user-provided flags và buildpack-provided flags có thể được kết hợp. Nếu cùng một JVM flag được cấu hình từ nhiều nguồn, cần kiểm tra behavior/precedence của Paketo runtime version và JVM thực tế; không suy rằng `JAVA_TOOL_OPTIONS` trong `docker image inspect .Config.Env` thể hiện mọi flags đã được tạo động.

Không cho secret vào JVM system properties, vì process diagnostics/logs có thể hiển thị. Đừng dùng `-Xmx` tùy tiện vượt container limit trong khi memory calculator đang quản lý JVM.

### 3.3 `BPL_*` khác `SPRING_*`

`BPL_JVM_THREAD_COUNT` là giả định cho JVM memory, còn `SERVER_TOMCAT_THREADS_MAX` ánh xạ Spring property `server.tomcat.threads.max` để điều khiển embedded Tomcat trong Spring Boot version tương ứng. Tên đều có "thread", nhưng chúng thuộc **hai subsystem** khác nhau.

Khi muốn điều chỉnh app runtime, xem Spring Boot properties; khi muốn điều chỉnh Paketo launch components, xem Paketo `BPL_*` documentation. Không tự đặt tên tùy ý rồi đoán framework sẽ hiểu.

## 4. `BPE_*`: chủ động nhúng launch environment từ lúc build

### 4.1 Ngoại lệ có thiết kế

Paketo **Environment Variables buildpack**, nếu có trong builder và được chọn, hiểu những biến bắt đầu bằng `BPE_*` trong **build stage** để tạo các biến hoặc quy tắc sửa biến cho **launch environment** của image.

| Cấu hình lúc build | Tác động dự kiến lúc launch |
| --- | --- |
| `BPE_APP_LABEL=from-image` | Thiết lập `APP_LABEL` (theo quy tắc override) |
| `BPE_DEFAULT_APP_LABEL=from-image` | Mặc định `APP_LABEL` nếu runtime chưa cấp |
| `BPE_OVERRIDE_APP_LABEL=from-image` | Override `APP_LABEL` theo quy tắc buildpack |
| `BPE_APPEND_JAVA_TOOL_OPTIONS=-Dfoo=bar` | Append vào `JAVA_TOOL_OPTIONS` |
| `BPE_PREPEND_JAVA_TOOL_OPTIONS=-Dfoo=bar` | Prepend vào `JAVA_TOOL_OPTIONS` |
| `BPE_DELIM_JAVA_TOOL_OPTIONS= ` | Dùng khoảng trắng làm delimiter khi append/prepend |

Các tên biến ở cột trái là **buildpack inputs**, còn biến ở cột phải là **launch outputs**. Vì vậy `BPE_*` chứng minh mệnh đề "build-time env không tự có tại runtime" có **ngoại lệ chỉ khi bạn cấu hình rõ việc nhúng**.

### 4.2 Ví dụ default và override

Giả sử builder có Paketo Environment Variables buildpack:

```bash
pack build example/cnb-env-demo:embedded \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env BP_JVM_VERSION=17 \
  --env BPE_DEFAULT_APP_LABEL=from-image
```

Với Spring app đọc property `app.label`, run **không cấp APP_LABEL** có thể dùng default `from-image`. Nếu dùng:

```bash
docker run --rm \
  -e APP_LABEL=blue \
  example/cnb-env-demo:embedded
```

thì theo semantics `BPE_DEFAULT_*`, runtime value `blue` có thể override default.

Đây là ví dụ **có điều kiện**: phải kiểm tra builder thực có buildpack này, buildpack được chọn và actual launch environment theo logs/app response. Nếu buildpack không hỗ trợ, biến `BPE_DEFAULT_APP_LABEL` có thể không được xử lý.

### 4.3 Nhúng JVM flag cho mọi deployment

Theo Spring Boot 3.3 Gradle plugin docs, có thể cấu hình:

```groovy
tasks.named("bootBuildImage") {
    environment["BP_JVM_VERSION"] = "17"
    environment["BPE_DELIM_JAVA_TOOL_OPTIONS"] = " "
    environment["BPE_APPEND_JAVA_TOOL_OPTIONS"] =
        "-XX:+HeapDumpOnOutOfMemoryError"
}
```

Flag có thể được áp dụng khi image launch nếu Paketo environment variables buildpack hỗ trợ. Đây là **quyết định tại build stage để chỉnh launch**, khác với `docker run -e JAVA_TOOL_OPTIONS=...` ở một deployment cụ thể.

**Không đặt secret vào `BPE_*`**: launch environment được nhúng có thể xem được qua image/layers/metadata hoặc cơ chế inspection, và mọi deployment của image có thể nhận nó.

### 4.4 Khi nào nên dùng `BPE_DEFAULT_*`?

Hợp lý cho một **mặc định không nhạy cảm** cần nhất quán, ví dụ label có thể override. Không hợp lý nếu dùng để cố định `SPRING_DATASOURCE_PASSWORD`, token, private key hay thông tin mật phụ thuộc staging/prod. Nếu mỗi môi trường có config riêng, dùng Docker/Kubernetes runtime config để giữ **cùng một image digest**.

## 5. Spring Boot runtime: profile, port, app properties

### 5.1 `SPRING_PROFILES_ACTIVE` và relaxed binding

Spring Boot đọc `SPRING_PROFILES_ACTIVE` thành `spring.profiles.active` khi ứng dụng **khởi động**.

```bash
docker run --rm -d \
  --name cnb-staging \
  -p 18080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  example/cnb-env-demo:0.0.1
```

Nếu có `application-staging.properties`, Spring config data có thể nạp profile-specific properties theo precedence. Không phải profile tên "staging" tự sinh database credentials: app cần cấu hình thực và nguồn secrets riêng.

**Đổi runtime profile không cần rebuild image** nếu artifact đã chứa resources/code cần dùng. Nhưng một process đang chạy không tự đọc environment mới khi bạn sửa deployment spec; cần tạo container/Pod mới hoặc cơ chế refresh riêng.

### 5.2 `SERVER_PORT` không phải `docker -p`

Ví dụ:

```bash
docker run --rm -d \
  --name cnb-port-demo \
  -e SERVER_PORT=9090 \
  -p 18090:9090 \
  example/cnb-env-demo:0.0.1
```

`SERVER_PORT=9090` yêu cầu Spring Boot listen cổng 9090. `-p 18090:9090` publish host port 18090 tới **container** port 9090. Nếu chỉ đổi `-p` mà app vẫn listen 8080, HTTP request tới 9090 trong container sẽ không được xử lý đúng.

Kubernetes `containerPort` cũng chủ yếu là metadata khai báo port; không tự ép Spring đổi `server.port`. Phải điều chỉnh Spring config nếu cần port khác.

### 5.3 App-specific `APP_LABEL`

Trong ví dụ, `application.properties` có:

```properties
app.label=from-file
```

Khi container có `APP_LABEL=blue` và không có property source có precedence cao hơn, Spring Boot ánh xạ env var thành `app.label` và app có thể đọc `blue`.

Đừng mặc định env thắng mọi trường hợp: Spring còn command-line args, system properties, config imports, `SPRING_APPLICATION_JSON` và các property sources tùy version/ứng dụng. Nếu CLI argument `--app.label=from-cli` được launcher thêm vào, nó có thể thắng giá trị từ environment theo Spring precedence.

### 5.4 Build-time `SPRING_PROFILES_ACTIVE` dễ gây hiểu lầm

Một người viết:

```groovy
tasks.named('bootBuildImage') {
    environment['SPRING_PROFILES_ACTIVE'] = 'prod'
}
```

Họ có thể kỳ vọng image tự chạy prod. Nhưng trong Spring Boot Gradle plugin, `bootBuildImage.environment` được truyền **tới builder**, không tự trở thành launch environment. Nếu muốn production profile:

```bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  example/cnb-env-demo:0.0.1
```

Nếu giai đoạn build có test JVM hoặc native/AOT compilation, environment có thể ảnh hưởng **chúng** tùy task/buildpack, nhưng đó là một chuyện khác. Không dùng Spring profile trong builder để quản lý môi trường triển khai của một executable-JAR image theo cách ngầm định.

## 6. Project Spring Boot Java 17+ để kiểm chứng

### 6.1 Cấu trúc

```text
cnb-env-demo/
├── pom.xml                      # Chọn Maven, hoặc
├── settings.gradle              # chọn Gradle
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/cnbenv/
│   │   │   ├── CnbEnvApplication.java
│   │   │   └── ProbeController.java
│   │   └── resources/application.properties
│   └── test/java/com/example/cnbenv/ProbeControllerTests.java
├── mvnw / mvnw.cmd               # Maven Wrapper nếu có
├── .mvn/wrapper/...
├── gradlew / gradlew.bat         # Gradle Wrapper nếu có
└── gradle/wrapper/...
```

Chỉ dùng **một** build system khi thực hành một nhánh. Wrapper cần được tạo bằng công cụ đáng tin và có các file hỗ trợ; không chỉ tạo script rỗng rồi gọi `./gradlew`.

### 6.2 Main class

File `src/main/java/com/example/cnbenv/CnbEnvApplication.java`:

```java
package com.example.cnbenv;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbEnvApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbEnvApplication.class, args);
    }
}
```

Đây là class Java 17+ hợp lệ **khi project có Spring Boot dependencies**. Không chạy `javac CnbEnvApplication.java` trần nếu chưa cung cấp Spring classes trên compiler classpath.

### 6.3 Probe controller không làm lộ secrets

File `src/main/java/com/example/cnbenv/ProbeController.java`:

```java
package com.example.cnbenv;

import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final Environment environment;

    public ProbeController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping(value = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        String label = environment.getProperty("app.label", "unset");
        String profiles = String.join(",", environment.getActiveProfiles());
        return "label=" + label + ";profiles=" + profiles;
    }
}
```

Controller trả **chỉ hai giá trị minh họa không nhạy cảm**, không dump `System.getenv()` hoặc tất cả properties. Không đưa password/API token vào endpoint.

Khi runtime `APP_LABEL=blue` và `SPRING_PROFILES_ACTIVE=staging`, response body kỳ vọng:

```text
label=blue;profiles=staging
```

Đây là **HTTP response body dự đoán từ Java method**, không phải log Docker đã chạy. Spring config precedence khác có thể ảnh hưởng giá trị thực.

### 6.4 `application.properties`

File `src/main/resources/application.properties`:

```properties
spring.application.name=cnb-env-demo
app.label=from-file
management.endpoints.web.exposure.include=health,info
```

Ở runtime, `APP_LABEL` có thể override `app.label` theo Spring Boot externalized configuration. Actuator `health` có ích cho smoke test, nhưng không cần expose `/actuator/env`. Trong production, chọn exposure/security hợp lý, không mở mọi management endpoint.

### 6.5 Integration test với profile riêng

File `src/test/java/com/example/cnbenv/ProbeControllerTests.java`:

```java
package com.example.cnbenv;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "app.label=from-test"
)
@ActiveProfiles("lab")
class ProbeControllerTests {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void readsExpectedEnvironment() {
        String body = rest.getForObject("/probe", String.class);
        assertEquals("label=from-test;profiles=lab", body);
    }
}
```

Test dùng random port, custom property `app.label=from-test` và `@ActiveProfiles("lab")` để kiểm soát profile thử nghiệm. Khi có global Spring test config hoặc extra profiles khác, assertion có thể cần điều chỉnh theo contract đó. Test này kiểm tra **ứng dụng trong JVM của build/test**, không chứng minh **OCI runtime image** đã nhận đúng env; vẫn cần chạy container thật.

## 7. Gradle `bootBuildImage.environment` — build time

### 7.1 Groovy DSL đầy đủ

`settings.gradle`:

```groovy
rootProject.name = 'cnb-env-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootBuildImage') {
    imageName = 'example/cnb-env-demo:0.0.1'
    environment['BP_JVM_VERSION'] = '17'
}
```

`bootBuildImage` được Spring Boot Gradle plugin tạo khi ứng dụng áp dụng Java/War plugin. `environment['BP_JVM_VERSION']` được gửi vào **CNB builder**, không phải Spring app runtime. `imageName` chỉ định tên OCI image; không phải tên Spring profile hoặc property `app.label`.

Theo Spring Boot Gradle docs, plugin có thể suy ra Java compatibility của project để yêu cầu buildpacks cài Java thích hợp. Ở đây explicit `BP_JVM_VERSION=17` để học cơ chế build. Nếu dùng builder khác, phải xác minh hỗ trợ tên biến này.

Chạy:

```bash
./gradlew clean build
./gradlew bootBuildImage
```

Lệnh `build` chạy Gradle checks/tests theo task graph thích hợp; `bootBuildImage` tạo OCI image từ archive, **không mặc định bảo đảm mọi test đã được chạy**. Tách test gate trước image build là thực hành tốt. Docker daemon phải truy cập được.

### 7.2 Kotlin DSL đầy đủ

`settings.gradle.kts`:

```kotlin
rootProject.name = "cnb-env-demo"
```

`build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("example/cnb-env-demo:0.0.1")
    environment.put("BP_JVM_VERSION", "17")
}
```

Đây là **Kotlin DSL tương đương**, không ghép cú pháp Groovy `environment['BP_JVM_VERSION']` vào `.gradle.kts`. Để đổi **runtime profile**, **không sửa block này**: cấp `SPRING_PROFILES_ACTIVE` khi run/deploy.

### 7.3 Thêm một BPE default có chủ đích

Nếu builder có Paketo Environment Variables buildpack, bạn có thể thêm vào block `bootBuildImage`:

```groovy
environment['BPE_DEFAULT_APP_LABEL'] = 'from-image'
```

Kết quả mong đợi là image có launch default của `APP_LABEL`. Không cần làm như vậy trong ví dụ mặc định vì phần 10 sẽ minh họa **cùng image** nhận APP_LABEL từ runtime. Hãy xem đây là thí nghiệm riêng; dùng BPE để nhúng dữ liệu làm thay đổi image release candidate.

## 8. Maven `spring-boot:build-image` — build time

### 8.1 POM đầy đủ

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

    <groupId>com.example</groupId>
    <artifactId>cnb-env-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-actuator</artifactId>
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
                        <name>example/cnb-env-demo:0.0.1</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Bên trong `<image><env>` là **builder environment** của Spring Boot Maven Plugin, không phải Spring Boot application runtime environment. Không có ý nghĩa rằng mọi container sẽ có `BP_JVM_VERSION` hoặc `SPRING_PROFILES_ACTIVE`.

Chạy:

```bash
./mvnw clean verify
./mvnw spring-boot:build-image
```

`spring-boot:build-image` đảm bảo Maven package lifecycle được thực hiện trước khi build OCI image. Khi cấu hình goal chạy trong lifecycle `package`, nên dùng biến thể `build-image-no-fork` theo tài liệu Spring Boot để tránh fork lifecycle không cần thiết.

### 8.2 Một cấu hình trông giống đúng nhưng sai mục đích

```xml
<image>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
        <SPRING_PROFILES_ACTIVE>prod</SPRING_PROFILES_ACTIVE>
    </env>
</image>
```

`SPRING_PROFILES_ACTIVE` ở đây **được gửi tới builder**, không tự đảm bảo Spring application khi launch image có profile prod. Nếu muốn production profile, cấp lúc chạy qua Docker/Kubernetes. Nếu có lý do đặc biệt cần image default, Paketo có `BPE_DEFAULT_SPRING_PROFILES_ACTIVE`, nhưng đó là artifact decision có chủ đích và thường không nên gắn chặt image chung vào một deployment environment.

### 8.3 Docker daemon và proxy

Spring Boot Maven `build-image` cần Docker daemon. Các biến `DOCKER_HOST`/`DOCKER_CONTEXT`/`DOCKER_CONFIG`/TLS configuration dùng để kết nối Docker engine **trong khi tạo image**; chúng không phải Spring properties. `HTTP_PROXY`/`HTTPS_PROXY` truyền vào builder có thể giúp builder tải JRE/runtime dependencies, nhưng runtime application muốn đi qua proxy **cần cấu hình riêng**.

## 9. `pack build --env` — không phải `docker run -e`

### 9.1 Tạo image từ executable JAR đã build

Sau `./gradlew build` ở ví dụ, file executable JAR thường là:

```text
build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar
```

Tạo image bằng Pack CLI:

```bash
pack build example/cnb-env-demo:pack \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env BP_JVM_VERSION=17
```

Tài liệu `pack build` nêu rõ `--env` và `--env-file` là **build-time environment variables, không tự có lúc image runtime**.

Nếu dùng:

```bash
pack build example/cnb-env-demo:pack \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env SPRING_PROFILES_ACTIVE=prod
```

đừng kết luận image sẽ launch với prod. Đó là builder env. Nếu đây là một executable JAR đã được build, Spring app thường không chạy ở builder dưới profile đó như một server production.

### 9.2 Tùy chọn `--env-file`

Một file build-time non-secret:

```text
BP_JVM_VERSION=17
```

Gọi:

```bash
pack build example/cnb-env-demo:pack \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env-file build-env.txt
```

Đừng nhầm Pack `--env-file` với Docker `docker run --env-file`. Hai công cụ có thể dùng tên tham số gần giống nhau, nhưng **giai đoạn và process nhận biến khác nhau**.

### 9.3 Build từ source khác build từ executable JAR

- `pack build --path build/libs/app.jar`: Paketo Java buildpacks xử lý JAR đã được compile/package.
- `pack build --path .`: nếu builder có Maven/Gradle buildpacks thích hợp, builder có thể compile source bằng công cụ build bên trong.
- `bootBuildImage`/`spring-boot:build-image`: Spring Boot plugin chuẩn bị executable archive rồi giao cho CNB build.

Vì vậy biến `BP_GRADLE_BUILD_ARGUMENTS` hoặc `BP_MAVEN_BUILD_ARGUMENTS` thường có ý nghĩa khi **builder đang chạy build tool trên source**; không phải cách thay Gradle host task graph trong `bootBuildImage`.

### 9.4 Host env truyền vào Pack khi được chỉ định

Pack CLI có dạng `--env VAR=VALUE` hoặc `--env VAR`. Với dạng không có `=VALUE`, CLI có thể đọc từ môi trường host hiện tại theo tài liệu của Pack. Đây là một **hành động truyền có chủ đích**, không phải Pack chuyển toàn bộ environment của máy developer vào image.

## 10. Thí nghiệm: một image, hai containers, hai runtime configs

### 10.1 Định danh image được build

Sau Gradle hoặc Maven image build:

```bash
docker image inspect example/cnb-env-demo:0.0.1 \
  --format '{{.Id}}'
```

Ghi lại image ID thật trên máy. Tag `example/cnb-env-demo:0.0.1` có thể bị gán lại sau này, nên với registry/CI nên dùng **image manifest digest** để theo dõi immutable artifact giữa staging và production.

### 10.2 Container A: staging

```bash
docker run --rm -d \
  --name cnb-env-a \
  -p 18080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  -e APP_LABEL=blue \
  example/cnb-env-demo:0.0.1
```

Đợi app ready rồi gọi:

```bash
curl --fail --silent --show-error \
  http://localhost:18080/probe
```

Với source mẫu và không có override khác, HTTP response body kỳ vọng:

```text
label=blue;profiles=staging
```

Đây là response do controller Java tạo, **không phải output của một lần Docker run đã thực thi**. Nếu curl chạy quá sớm, hãy dùng health check/retry có giới hạn và `docker logs cnb-env-a`.

### 10.3 Container B: production-like

Không rebuild, chạy chính image đó với biến khác:

```bash
docker run --rm -d \
  --name cnb-env-b \
  -p 18081:8080 \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e APP_LABEL=green \
  example/cnb-env-demo:0.0.1
```

Gọi:

```bash
curl --fail --silent --show-error \
  http://localhost:18081/probe
```

Kết quả kỳ vọng:

```text
label=green;profiles=prod
```

App cùng code/classes, **runtime env khác nhau**. Nếu có profile-specific resource trong JAR thì Spring có thể đọc thêm tùy profile, nhưng thí nghiệm chỉ kiểm tra `APP_LABEL` và `SPRING_PROFILES_ACTIVE`.

### 10.4 Chứng minh thực sự cùng image

```bash
docker inspect cnb-env-a --format '{{.Image}}'
docker inspect cnb-env-b --format '{{.Image}}'
docker image inspect example/cnb-env-demo:0.0.1 --format '{{.Id}}'
```

Nếu hai `.Image` giống nhau, hai containers được tạo từ **cùng local image ID**. Trong registry, dùng digest để tránh tag bị dịch chuyển. Thay runtime environment không tạo một image ID mới.

Đừng in đầy đủ `docker inspect --format '{{json .Config.Env}}'` nếu các container thật chứa secrets. Nó có thể lộ database password/credentials. Chỉ dùng probe không nhạy cảm hoặc inspector có kiểm soát.

Dọn lab:

```bash
docker stop cnb-env-a cnb-env-b
```

Vì containers dùng `--rm` nên được xóa khi dừng. Trong CI song song, dùng tên/cổng riêng để tránh xung đột với jobs khác.

### 10.5 Hai phép kiểm tra bổ sung

**Kiểm tra default không có APP_LABEL:**

```bash
docker run --rm -d \
  --name cnb-env-default \
  -p 18082:8080 \
  example/cnb-env-demo:0.0.1
```

Khi không cấp APP_LABEL, controller có thể trả `label=from-file;profiles=`, nếu không có BPE embedded default và không có env/CLI config khác.

**Kiểm tra server port:**

```bash
docker run --rm -d \
  --name cnb-env-9090 \
  -e SERVER_PORT=9090 \
  -p 18090:9090 \
  example/cnb-env-demo:0.0.1
```

Gọi `http://localhost:18090/probe`, không gọi `18090:8080`. Dừng cả hai container lab sau thử nghiệm.

## 11. Docker Compose và Kubernetes: runtime environment

### 11.1 Compose `environment`

Ví dụ `compose.yaml`:

```yaml
services:
  app:
    image: example/cnb-env-demo:0.0.1
    ports:
      - "18080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: staging
      APP_LABEL: blue
      BPL_JVM_THREAD_COUNT: "100"
```

`docker compose up` ở đây tạo container từ **image có sẵn**, không tự gọi Paketo build vì không có `build:`. `environment` là **runtime env của service**.

Nếu file Compose có `build.args`, đó là **Dockerfile ARG** khi Docker build, không tự tương đương `bootBuildImage.environment` hoặc `pack build --env`. Đừng trộn lẫn Dockerfile build với CNB builder lifecycle.

### 11.2 Compose `.env` vs `env_file`

- `.env` trong project hoặc `docker compose --env-file` thường dùng cho **Compose variable interpolation**.
- Service `environment:` trực tiếp tạo runtime env.
- Service `env_file:` đọc biến vào environment của service/container.
- `docker compose config` giúp xem resolved model nhưng có thể hiện giá trị nhạy cảm; không đưa output đầy đủ lên public log.

Ví dụ substitution bằng Compose syntax:

```yaml
services:
  app:
    image: example/cnb-env-demo:0.0.1
    environment:
      SPRING_PROFILES_ACTIVE: ${APP_PROFILE:-staging}
      APP_LABEL: ${APP_LABEL:-blue}
```

Trong YAML, `${APP_PROFILE:-staging}` là expression Compose thay bằng biến host hoặc default `staging`. Nó **không phải** cú pháp Spring Boot property placeholder. Khi service tạo container, Spring mới nhìn thấy biến `SPRING_PROFILES_ACTIVE` đã được Compose resolve.

Có file `.env` **không có nghĩa** mọi key tự được đưa vào container nếu chúng không được tham chiếu trong service model hoặc không dùng `env_file`.

### 11.3 Kubernetes `env` và `envFrom`

Trích đoạn cấu hình container trong Deployment template:

```yaml
spec:
  template:
    spec:
      containers:
        - name: app
          image: registry.example.com/team/cnb-env-demo:0.0.1
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: APP_LABEL
              value: "green"
            - name: BPL_JVM_THREAD_COUNT
              value: "100"
```

Đây là **trích đoạn minh họa**, chưa phải Deployment đầy đủ; cần selector, metadata, resource policies và image registry thực tế. `env` là runtime config được cấp cho Pod khi container khởi động. Nó **không rebuild image**. Thay Pod template trong Deployment thường tạo rollout Pod mới để biến có hiệu lực.

### 11.4 Secrets và ConfigMaps

Các giá trị thông thường như label có thể từ ConfigMap; password/API tokens có thể từ Kubernetes Secret hoặc external secret manager.

```yaml
env:
  - name: APP_LABEL
    valueFrom:
      configMapKeyRef:
        name: app-settings
        key: label
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
```

Kubernetes Secret không tự đảm bảo không thể bị xem: phải quản lý RBAC, encryption at rest, audit logs, secret rotation, Pod permissions và log redaction. Nhưng runtime secret injection vẫn phù hợp hơn việc đóng password vào `BPE_*`/`build.gradle`/OCI layers.

## 12. Những lỗi suy luận cần tránh

### 12.1 "Có biến trong build log, vậy container có biến đó"

**Sai.** Build log chỉ chứng minh biến đã tác động một giai đoạn builder/tooling. Chỉ container environment/launch scripts hoặc app runtime check mới chứng minh giá trị khi chạy.

### 12.2 "Thêm `-e BP_JVM_VERSION=21` để nâng JVM"

**Sai.** Runtime env không tự thay layers. Muốn đổi Java runtime, cấu hình builder và build image mới, sau đó verify version Java/bytecode.

### 12.3 "Đặt `SPRING_PROFILES_ACTIVE=prod` vào Gradle image environment"

**Không đúng mục đích.** `bootBuildImage.environment` là builder env. Dùng Docker/Compose/Kubernetes runtime env để chọn profile. Nếu thật sự muốn embedded default, dùng BPE khi builder hỗ trợ và hiểu hậu quả của image-specific default.

### 12.4 "Pack env-file giống Docker env-file"

**Sai.** `pack build --env-file` tạo build-time environment cho builder; `docker run --env-file` tạo runtime environment cho container. Đừng dùng chung một file secrets cho cả hai vì dễ rò thông tin.

### 12.5 "BPE giống BPL"

**Sai.** `BPE_*` được set **ở build time** để Paketo Environment Variables buildpack thay **launch environment**. `BPL_*` được đưa vào **ở runtime** để các launch components của Paketo đọc giá trị khi container khởi động.

### 12.6 "Mọi build-time env đều biến mất hoàn toàn"

**Không chính xác.** Giá trị có thể **ảnh hưởng Java version**, buildpack selection, layers, generated source, SBOM hoặc launch env nếu dùng BPE. Điểm đúng là **không tự thừa kế mọi tên/value env của builder vào container**.

### 12.7 "Mỗi môi trường cần build một image"

Thường **không cần** nếu ứng dụng dùng externalized runtime config. Xây một image, kiểm thử/promote theo digest rồi dùng runtime env riêng cho staging/prod. Nếu phải đổi code, Java runtime, native build, CA package hoặc system libraries, đó mới thường là lý do tạo image mới.

## 13. Build proxy khác runtime proxy

Khi builder cần tải dependency qua proxy, Spring Boot Gradle plugin có thể truyền:

```groovy
tasks.named('bootBuildImage') {
    environment['HTTP_PROXY'] = 'http://proxy.example.org:3128'
    environment['HTTPS_PROXY'] = 'http://proxy.example.org:3128'
}
```

Đây là **builder network config**; địa chỉ chỉ minh họa. Không có nghĩa Java app chạy trong image tự dùng cùng proxy. Nếu runtime cần proxy HTTPS, phải cấu hình launcher/JVM/HTTP client riêng, có thể qua `JAVA_TOOL_OPTIONS` hay client-specific settings. Không phải mọi Java HTTP client đều tôn trọng `HTTP_PROXY`.

Với proxy có authentication, **đừng commit user/password trong proxy URL**. Dùng cơ chế credential/secret injection được chấp thuận và bảo vệ build logs/caches. Nếu gặp TLS trust error do corporate CA, cài trust certificate đúng cách, không vô hiệu hóa certificate validation để "cho qua".

## 14. Secrets: khác giai đoạn nhưng đều phải bảo vệ

### 14.1 Build secrets

Token để tải Maven/Gradle dependency private có thể được cần **trong builder**. Nhưng một biến `--env MY_TOKEN=...` không phải cơ chế secrets an toàn mặc định. Nó có thể xuất hiện trong command history, logs, cache, process/config metadata. Sử dụng **CNB service bindings**, secret mounts hoặc credential mechanisms chính thức của builder/platform phù hợp.

Không nhúng build tokens vào `application.properties`, JAR hoặc `BPE_*`. Không công khai output `--debug` nếu chứa URL nội bộ/token.

### 14.2 Runtime secrets

Database password, API keys, TLS private keys thường được cấp **khi container chạy** bằng secret manager/Kubernetes Secret/mounted file/runtime injection thích hợp. Không encode secrets vào OCI image, Gradle `image.environment`, Maven POM hoặc BPE default.

Runtime env cũng không tự "bảo mật tuyệt đối": người có quyền inspect Pod/container hoặc process có thể xem; hạn chế quyền, redaction và rotation rất quan trọng.

### 14.3 Config public khác config private

Các giá trị `APP_LABEL=blue`, `SPRING_PROFILES_ACTIVE=staging` thường không nhạy cảm. Nhưng `SPRING_DATASOURCE_PASSWORD` hoặc `API_TOKEN` là secret. Đối với bài lab, controller chỉ trả label/profiles; **không thêm endpoint trả toàn bộ `System.getenv()`**.

### 14.4 Không dùng runtime image debug để lộ dữ liệu

`docker inspect <container>` có thể chứa toàn bộ `Config.Env`. Tránh chạy `docker inspect --format '{{json .Config.Env}}'` trong CI logs có quyền rộng. Nếu cần so sánh môi trường, chỉ log **tên các biến** hoặc giá trị đã redacted, không log secrets.

## 15. Runtime diagnostics và launcher

### 15.1 Image metadata không đầy đủ launch-time JVM flags

`docker image inspect` hiển thị image config metadata; tuy nhiên Paketo runtime có launcher/profile scripts và có thể tạo `JAVA_TOOL_OPTIONS` động theo cgroup memory limit và `BPL_*`. Vì vậy không nhìn thấy toàn bộ flags trong `Config.Env` **không chứng minh** runtime component không hoạt động.

Có thể kiểm tra:

```bash
docker image inspect example/cnb-env-demo:0.0.1 \
  --format '{{.Id}}'

docker image inspect example/cnb-env-demo:0.0.1 \
  --format '{{.Config.Entrypoint}}'

docker inspect cnb-env-a --format '{{.Image}}'
```

Nếu image dùng CNB launcher, đổi `--entrypoint` trực tiếp có thể **bỏ qua cách setup environment** mà buildpack dựa vào. Một số Paketo run images không có shell; `docker exec ... sh` không phải bước kiểm tra đáng tin ở mọi image.

### 15.2 Diễn giải build logs

Trong Spring Boot `bootBuildImage` hoặc `spring-boot:build-image` build logs, tìm:

- Builder image/buildpack IDs và versions.
- Java runtime dependency version được buildpack lựa chọn.
- Có step detect/build/export và image name/digest không.
- Có nhận `BP_JVM_VERSION` không, hay builder bỏ qua.
- Có Paketo Environment Variables buildpack xử lý BPE không.
- Có secrets bị log do bật quá nhiều verbose debug không.

Không kết luận từ **một dòng shell `export BP_JVM_VERSION=17`** rằng builder đã dùng nó; cần xét plugin forwarding config và logs.

### 15.3 Kiểm tra bằng Java 17 thuần (không Spring)

Một ví dụ để tách **runtime environment** khỏi build system:

```java
public final class EnvProbe {
    public static void main(String[] args) {
        String value = System.getenv().getOrDefault("APP_LABEL", "unset");
        System.out.println("APP_LABEL=" + value);
    }
}
```

Lưu file `EnvProbe.java`. Trên JDK 17+ trong cùng thư mục:

```bash
javac EnvProbe.java
APP_LABEL=blue java EnvProbe
```

Stdout chính xác của chương trình:

```text
APP_LABEL=blue
```

Nếu không cấp biến (ví dụ trên hệ thống có `env -u`):

```bash
env -u APP_LABEL java EnvProbe
```

Stdout:

```text
APP_LABEL=unset
```

Chương trình này biên dịch **một lần** rồi chạy với nhiều environment; `javac` không cần biết `APP_LABEL`. Nó minh họa cơ chế Java process environment, không cần Cloud Native Buildpacks để chứng minh.

## 16. Windows PowerShell

PowerShell dùng `$env:VAR` để cấp biến cho process trong session, không dùng Bash `VAR=value command`.

```powershell
$env:BP_JVM_VERSION = "17"
$env:APP_LABEL = "blue"
```

Các lệnh trên vẫn chỉ cấu hình **host process environment**, không tự chép tất cả biến vào builder hay OCI image. Với Gradle, nên dùng `environment.put(...)`/`environment['...']` đúng DSL; với Pack CLI, truyền `--env BP_JVM_VERSION=17`.

Ví dụ một dòng trên PowerShell (không dùng shell continuation):

```powershell
pack build example/cnb-env-demo:pack --builder paketobuildpacks/builder-jammy-base --path build\libs\cnb-env-demo-0.0.1-SNAPSHOT.jar --env BP_JVM_VERSION=17
```

Run container với **runtime** env:

```powershell
docker run --rm -d --name cnb-win -p 18080:8080 -e SPRING_PROFILES_ACTIVE=staging -e APP_LABEL=blue example/cnb-env-demo:pack

(Invoke-WebRequest -Uri "http://localhost:18080/probe").Content

docker stop cnb-win
```

Dòng `.Content` theo mã Java mẫu sẽ là `label=blue;profiles=staging` nếu server đã ready. Windows Docker Desktop phải chạy mode Linux containers phù hợp với Paketo builder/run image, nếu không có thể gặp lỗi OS/platform không tương thích dù biến đúng.

## 17. Image identity và CI/CD

### 17.1 Tag không phải digest

`example/cnb-env-demo:0.0.1` là **tag có thể bị gán lại**. Với một registry, dùng immutable digest (ví dụ image ref có `@sha256:...` do registry cung cấp) để đảm bảo staging/prod pull đúng byte image đã được QA, thay vì dựa hoàn toàn vào tag.

Ghi build inputs cần thiết: commit hash, build tool, plugin version, builder/run image digest, Paketo buildpacks, Java compatibility và các `BP_*`/`BPE_*` không nhạy cảm. Runtime config lưu ở deployment spec/secret reference, không đóng toàn bộ vào artifact metadata.

### 17.2 Khi nào cần image mới?

**Cần cân nhắc rebuild và QA lại** nếu đổi:

- Java runtime version `BP_JVM_VERSION`, JVM provider/type, `BP_JVM_JLINK_ENABLED`.
- Builder/buildpacks/run image/OS stack/CA packages.
- Source code, runtime dependency versions, Spring Boot version.
- Native-image build mode hoặc source/AOT compilation.
- `BPE_*` launch defaults được nhúng trong artifact.
- Build process thật sự biến đổi resource/classes theo input mới.

**Thông thường không cần rebuild** nếu chỉ đổi:

- `SPRING_PROFILES_ACTIVE` cho staging/prod.
- `APP_LABEL` hoặc runtime feature flag.
- Database URL/password được externalized.
- `SERVER_PORT`/network routing trong giới hạn app hỗ trợ.
- `BPL_JVM_THREAD_COUNT` hoặc `JAVA_TOOL_OPTIONS` runtime tuning.

Ngay cả khi image không đổi, runtime config mới **vẫn phải được smoke/integration-test** trước production rollout.

### 17.3 Pipeline có kiểm soát

1. Checkout đúng source/commit, dùng Maven/Gradle Wrapper đã được review.
2. Chạy tests, tạo executable JAR.
3. Tạo OCI image qua Paketo với builder và `BP_*` đã ghim/ghi nhận.
4. Quét image/dependencies, kiểm tra runtime Java và HTTP smoke test.
5. Push image, lấy registry manifest digest thực.
6. Deploy staging **theo digest**, cấp env staging/secret refs khi tạo Pod/container.
7. Kiểm tra staging với dữ liệu/secret đã được phép.
8. Promote **cùng digest** sang production, chỉ thay runtime env/secret refs/resources.
9. Thu log/metrics và có rollback theo digest.
10. Khi đổi build inputs thực sự, tạo **release candidate mới**, lặp lại gates.

**Không viết image lại trong stage production** rồi vẫn tuyên bố "đã kiểm tra ở staging" nếu digest khác. Ngoại lệ chỉ có thể được chấp thuận bởi quy trình reproducible build + attestation chặt, nhưng mô hình đơn giản là **promote cùng image digest**.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `BP_JVM_VERSION` không đổi Java lúc `docker run -e` | Đây là build-time Paketo config | Rebuild image qua plugin/pack, kiểm tra Java runtime |
| `SPRING_PROFILES_ACTIVE` đặt trong `bootBuildImage.environment` nhưng app vẫn default | Builder env không tự là launch env | Cấp runtime `docker run -e`/Kubernetes `env` |
| Host `export APP_LABEL=blue` nhưng container không nhận | Host env không tự propagate | Cấp runtime env rõ ràng |
| `pack build --env-file` có profile nhưng app không nhận | Pack env-file chỉ dành build | Dùng Docker runtime env-file hoặc Compose |
| `BPE_DEFAULT_APP_LABEL` bị bỏ qua | Builder không có Paketo Environment Variables buildpack | Kiểm tra buildpacks/logs rồi tạo image đúng |
| Runtime không override `BPE_*` | Có thể dùng OVERRIDE thay DEFAULT hoặc Spring property source khác cao hơn | Xem BPE action và Spring precedence |
| `BPL_JVM_THREAD_COUNT` không đổi HTTP response | Cấu hình JVM memory, không phải Spring app property | Xem JVM launch flags/memory calculator |
| `BPL_*` không có hiệu lực | Image thiếu Paketo runtime component hoặc launcher bị bỏ qua | Xem buildpacks và entrypoint |
| `JAVA_TOOL_OPTIONS` bị ghép kỳ lạ | BPE append thiếu delimiter hoặc nhiều nguồn cung cấp JVM flag | Kiểm tra `BPE_DELIM_JAVA_TOOL_OPTIONS` và startup flags |
| `SERVER_PORT=9090` mà curl host không vào | Docker mapping sai hoặc app chưa ready | Dùng `-p HOST:9090` và xem logs |
| Java tests pass nhưng app container fail | Test chạy ở build JVM, runtime config khác | HTTP smoke test final image |
| `bootBuildImage` task not found | Boot và Java/War plugin chưa apply ở đúng module | Xem `:module:tasks --all` |
| Maven build-image không tìm Docker daemon | DOCKER_CONTEXT/HOST/TLS sai | Kiểm tra Docker daemon connection |
| Buildpack không hiểu `BP_*` | Builder khác Paketo hoặc biến không được hỗ trợ | Kiểm tra builder/buildpack docs |
| Builder proxy OK nhưng runtime HTTPS fail | Proxy/truststore runtime khác | Cấu hình runtime proxy/CA riêng |
| Một tag có behavior khác sau pull | Tag mutable trỏ digest khác | Pin/publish digest, kiểm tra identity |
| Thay env nhưng Pod cũ vẫn dùng giá trị cũ | Container chưa restart/rollout | Tạo Pod mới theo deployment model |
| Image chứa secret | Dùng BPE/ARG/ENV/source để nhúng credentials | Rotate secret, sửa pipeline, rebuild image |
| `docker inspect` log lộ secrets | In toàn bộ Config.Env | Hạn chế inspection, redact values và RBAC |
| CNB image không có shell | Run image tối giản | Dùng debug/probe ngoài container thay vì ép `sh` |
| `pack --path .` khác `bootBuildImage` | Một bên build từ source, bên kia xử lý JAR đã build | So artifact, buildpacks, task graph |
| Java runtime thấp hơn class file target | Build/runtime Java không tương thích | Đồng bộ `BP_JVM_VERSION`, compiler target và test |
| Đổi `-p` nhưng server vẫn listen cổng cũ | `-p` chỉ publish, không set Spring `server.port` | Set `SERVER_PORT` hoặc dùng correct port mapping |
| App đọc giá trị file thay vì env | Sai tên env var hoặc nguồn precedence cao hơn | Kiểm tra `APP_LABEL` và Spring property sources |
| BPE đưa profile prod vào mọi image | Chọn sai default/override strategy | Xóa BPE env-specific, deploy runtime config theo môi trường |

### Quy trình điều tra ngắn

1. Xác định biến có tác động **build**, **launch runtime**, hay **image-embedded**.
2. Xem đúng plugin task và image reference/digest.
3. Kiểm tra builder/buildpack version và biến có được truyền qua cấu hình tool thật không.
4. Xác minh container được tạo mới với env runtime mong đợi.
5. Kiểm tra `/probe`, `/actuator/health` và log startup, không lấy build log thay runtime evidence.
6. Với memory flag, kiểm tra JVM/memory calculator; với app property, kiểm tra Spring.
7. Với secret, tránh log giá trị, dùng RBAC/secret manager.
8. Nếu cần Java/runtime library khác, rebuild image; nếu chỉ profile/app label, không rebuild.

## 19. Bài thực hành

### A. Phân loại biến

Xếp các biến sau vào builder-only, runtime launch, embedded launch default hoặc host/tooling:

```text
BP_JVM_VERSION
BP_JVM_TYPE
BPL_JVM_HEAD_ROOM
BPL_JVM_THREAD_COUNT
BPE_DEFAULT_APP_LABEL
BPE_APPEND_JAVA_TOOL_OPTIONS
SPRING_PROFILES_ACTIVE
SERVER_PORT
APP_LABEL
JAVA_TOOL_OPTIONS
HTTP_PROXY
DOCKER_HOST
```

Giải thích tại sao `HTTP_PROXY` và `JAVA_TOOL_OPTIONS` có thể được đọc ở nhiều process tùy **giai đoạn được cấp**, còn `DOCKER_HOST` là cấu hình Docker client/daemon connection.

### B. Gradle build và hai containers

1. Dựng project phần 6–7.
2. Chạy `./gradlew clean build` và `./gradlew bootBuildImage`.
3. Ghi local image ID, builder và Java major.
4. Chạy container A với `APP_LABEL=blue`, `SPRING_PROFILES_ACTIVE=staging`.
5. Chạy container B với `APP_LABEL=green`, `SPRING_PROFILES_ACTIVE=prod`.
6. So hai response HTTP, so image ID; không rebuild giữa hai lượt.
7. Kết luận image identity không đổi dù runtime config thay.

### C. Maven build-image

1. Dùng POM mẫu ở phần 8 và mã Java tương tự.
2. Chạy Maven tests rồi `spring-boot:build-image`.
3. Đọc `<image><env>` và nêu vì sao nó **không tự tạo runtime profile**.
4. Run với profile staging và prod qua `docker run -e`.
5. Chứng minh bằng HTTP response và image ID.

### D. Pack CLI

1. Build executable JAR bằng Gradle/Maven.
2. Dùng `pack build --path <actual-jar> --env BP_JVM_VERSION=17`.
3. Run image với `APP_LABEL`/`SPRING_PROFILES_ACTIVE`.
4. Trên nhánh lab, thử `pack --env SPRING_PROFILES_ACTIVE=prod` và kiểm tra runtime không tự nhận.
5. Phân biệt `pack --env-file` với Docker `run --env-file`.

### E. BPE default

1. Chọn builder Paketo có Environment Variables buildpack.
2. Build với `BPE_DEFAULT_APP_LABEL=from-image`.
3. Run không có APP_LABEL; ghi label thực tế.
4. Run lại với `-e APP_LABEL=blue`; so kết quả.
5. Giải thích vì sao BPE default là **artifact configuration** và không nên chứa secret.

### F. JVM tuning lúc chạy

1. Chạy hai containers từ cùng image với `BPL_JVM_THREAD_COUNT` khác nhau.
2. Giữ memory limit rõ ràng và đọc Paketo/JVM diagnostics phù hợp.
3. Không kỳ vọng `/probe` đổi vì controller không dùng biến đó.
4. Nếu memory calculator vắng mặt, nêu giới hạn của thí nghiệm thay vì tự tuyên bố thành công.

### G. Compose và Kubernetes

1. Viết Compose service `environment` cho staging.
2. Giải thích `.env` vs `env_file`.
3. Viết Kubernetes Pod fragment `env` và `secretKeyRef` cho prod.
4. Nêu cách sửa deployment env và rollout Pod, không rebuild image.
5. Trình bày nơi cần bảo vệ secrets và log redaction.

### H. Phản biện cấu hình sai

Một người chạy:

```bash
pack build example/cnb-env-demo:wrong \
  --builder paketobuildpacks/builder-jammy-base \
  --path build/libs/cnb-env-demo-0.0.1-SNAPSHOT.jar \
  --env SPRING_PROFILES_ACTIVE=prod

docker run --rm example/cnb-env-demo:wrong
```

Họ nói image chắc chắn dùng `prod`. Hãy chỉ ra `pack --env` ở builder; để Spring chạy prod phải truyền `SPRING_PROFILES_ACTIVE=prod` khi launch hoặc sử dụng **BPE launch default** có chủ đích và được hỗ trợ. Trình bày bằng chứng nào sẽ quyết định ai đúng.

### I. Báo cáo dựa trên kết quả thật

```text
Module:
Spring Boot plugin version:
Builder image/buildpacks version:
Build command:
Build-time vars (non-sensitive):
Image name + local ID + registry digest:
Container A env (non-sensitive):
Container A HTTP status/body:
Container B env (non-sensitive):
Container B HTTP status/body:
Two containers same image ID?:
BPE default used? Result:
BPL runtime flags used? Evidence:
Secrets injection source (no values):
Conclusion build vs runtime:
```

Đây là **mẫu báo cáo để điền kết quả thực**, không phải một report pass có sẵn. Nếu không có Docker/buildpacks trong môi trường học, hãy ghi **chưa chạy được smoke test**, không tự tạo HTTP 200 hoặc SHA/digest tưởng tượng.

## 20. Checklist kiến thức và vận hành

- [ ] Đã xác định đúng nơi biến được cấp: host, CNB builder, image launch, Docker/Kubernetes runtime.
- [ ] `BP_JVM_VERSION` khớp Java compiler compatibility và builder có hỗ trợ.
- [ ] Gradle `bootBuildImage.environment`/Maven `image.env` chỉ chứa builder config có chủ đích.
- [ ] `pack build --env` được hiểu là build-time, không runtime.
- [ ] `BPL_*` chỉ dùng khi image có Paketo launch component tương ứng.
- [ ] Nếu dùng `BPE_*`, đã hiểu đó là **nhúng/sửa launch env** của image.
- [ ] Không nhúng credentials vào `BPE_*`, build scripts, image layers hoặc debug logs.
- [ ] `SPRING_PROFILES_ACTIVE`/`APP_LABEL` được cấp tại runtime theo môi trường.
- [ ] `SERVER_PORT` và Docker/Kubernetes port mapping khớp.
- [ ] Test ứng dụng trong build và smoke test image cuối với runtime env thật.
- [ ] Dùng image ID/digest, không chỉ tag mutable, để chứng minh staging/prod chung artifact.
- [ ] Runtime secrets được cấp bằng cơ chế riêng, có RBAC/redaction/rotation.
- [ ] Đổi build-time config → tạo image mới và QA; đổi runtime config → rollout container mới.
- [ ] Không dump toàn bộ môi trường qua HTTP/Actuator hoặc CI log.
- [ ] Có kết quả HTTP, logs, metadata thực cho mọi kết luận "đã chạy".

## 21. Tài liệu chính thức

- Spring Boot 3.3.13 Maven Plugin — Packaging OCI Images, `image.env`: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html
- Spring Boot 3.3.13 Gradle Plugin — Packaging OCI Images, `bootBuildImage.environment`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html
- Spring Boot 3.3 — Externalized Configuration, env vars và property source precedence: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Paketo — How To Configure Buildpacks: `BP_*`/`BPL_*`/`BPE_*`: https://paketo.io/docs/howto/configuration/
- Paketo — How to Build Java Apps, Java version và runtime JVM: https://paketo.io/docs/howto/java/
- Paketo — Java Buildpack Reference, memory calculator: https://paketo.io/docs/reference/java-reference/
- Cloud Native Buildpacks — `pack build` CLI, `--env`/`--env-file` build-time: https://buildpacks.io/docs/tools/pack/cli/pack_build/
- Cloud Native Buildpacks — Launch process: https://buildpacks.io/docs/for-buildpack-authors/how-to/write-buildpacks/specify-launch-processes/
- Docker — `docker container run` options: https://docs.docker.com/reference/cli/docker/container/run/
- Docker Compose — Environment precedence: https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/
- Kubernetes — Define Environment Variables: https://kubernetes.io/docs/tasks/inject-data-application/define-environment-variable-container/
- Kubernetes — Secrets: https://kubernetes.io/docs/concepts/configuration/secret/

**Ghi nhớ:** `BP_*` là cấu hình build-time Paketo, `BPL_*` dành cho các runtime launch components, `BPE_*` là cơ chế **nhúng launch env từ lúc build**, còn Spring properties như `SPRING_PROFILES_ACTIVE`/`SERVER_PORT` nên được cấp khi chạy nếu thay đổi theo môi trường. **`pack build --env`, Gradle `bootBuildImage.environment` và Maven `image.env` không đồng nghĩa Docker `run -e`.** Hãy kiểm chứng bằng **cùng image digest, hai containers, hai runtime configs và kết quả HTTP thật**, không rebuild chỉ để thay một profile hay label.
