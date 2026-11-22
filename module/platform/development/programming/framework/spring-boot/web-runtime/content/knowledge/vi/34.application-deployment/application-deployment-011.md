# Ranh giới giữa yêu cầu runtime với công cụ đóng gói và nền tảng triển khai

> **Module:** Spring Boot - web-runtime · **Nhóm:** Triển khai ứng dụng. Bài học phân định trách nhiệm giữa **mã ứng dụng/JVM/Spring Boot khi chạy**, **Maven/Gradle khi biên dịch và tạo artifact**, **Dockerfile/Cloud Native Buildpacks khi tạo OCI image**, và **Docker/Kubernetes/PaaS khi triển khai process, mạng, secrets, health checks và tài nguyên**. Các ranh giới này là điều kiện để tìm đúng nguyên nhân khi “build xanh nhưng production lỗi”. Ví dụ áp dụng **Java 17+, Spring Boot 4.1.2, Spring MVC, Actuator, Maven, Docker và Kubernetes**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả năm thời điểm: **source/dependency resolution → compile/test → JAR/WAR packaging → image build → deploy/runtime**, đồng thời nêu những điều mỗi thời điểm không bảo đảm.
2. Nêu **runtime contract** của Spring Boot 4.1.2: Java tối thiểu 17; dependencies/classpath; port, cấu hình, secrets, file permissions, CPU/RAM, kết nối ngoài, health và shutdown.
3. Phân biệt `mvn package`, `spring-boot:repackage`, `java -jar`, Gradle `bootJar`, Boot `build-image`, `docker build`, `docker run`, image push và Kubernetes `Deployment`.
4. Giải thích `BOOT-INF/classes`, `BOOT-INF/lib`, `Main-Class`/`Start-Class`, executable JAR và sự khác biệt WAR/embedded server/native binary.
5. Chỉ ra trách nhiệm của `Dockerfile`, JRE/base image, Cloud Native Buildpacks, image architecture, OCI digest, registry và supply-chain checks.
6. Thiết kế mapping `server.port` ↔ `containerPort` ↔ Service `targetPort` ↔ Ingress/LB, không nhầm `EXPOSE` là mở port.
7. Cấp `SPRING_PROFILES_ACTIVE`, environment variables, `JAVA_TOOL_OPTIONS`, mounted Secret/`configtree:` **khi chạy**, không bake secrets vào artifact.
8. Phân biệt startup/liveness/readiness probes, `server.shutdown=graceful`, SIGTERM, preStop và giới hạn `terminationGracePeriodSeconds`.
9. Chạy project Maven Spring Boot, test bằng JUnit real random port, tạo Docker image, lập Deployment/Service tham khảo và kiểm tra API/health qua các môi trường.
10. Có checklist điều tra `UnsupportedClassVersionError`, `no main manifest attribute`, `ImagePullBackOff`, `CrashLoopBackOff`, OOMKilled, readiness fail, 502 proxy và lỗi graceful termination.

## 2. Bản đồ trách nhiệm từ source code tới HTTP response

~~~text
Git commit / source code
       |
       v
[1] MAVEN / GRADLE
    resolve deps -> compile -> test -> package
       |
       v
Executable JAR/WAR (application + Boot loader + libraries)
       |
       v
[2] IMAGE BUILDER: Dockerfile hoặc Cloud Native Buildpacks
    JRE/OS libraries + artifact + image entrypoint + layers
       |
       v
OCI image: registry/repository@sha256:digest
       |
       v
[3] DEPLOYMENT PLATFORM: Docker/Kubernetes/PaaS
    pull image, schedule instances, inject config/secrets,
    mount storage, set networking/probes, resources/limits,
    route traffic, restart/scale/rollout
       |
       v
[4] RUNTIME: JVM + Spring Boot + embedded server
    start, bind config, listen on port, handle HTTP,
    check health, send logs, receive SIGTERM, shut down
       |
       v
HTTP client / downstream services
~~~

Một lần deploy không phải một thao tác đơn lẻ. Maven hoàn thành trách nhiệm build không bảo đảm Kubernetes đã pull image; Docker image được tạo không bảo đảm startup health; Kubernetes Pod RUNNING không chứng minh user có thể dùng API; HTTP 200 ở localhost không chứng minh public TLS, DNS, proxy headers và security đã đúng.

### 2.1. Ma trận “ai sở hữu lỗi?”

| Hành vi/cấu hình | Tầng sở hữu chính | Tầng phối hợp |
| --- | --- | --- |
| Java compiler target, annotation processors | Maven/Gradle + JDK build | Developer/CI |
| Dependency version/upgrade | Build configuration | Security/SBOM tooling |
| Nested libraries, executable manifest | Boot Maven/Gradle plugin | Runtime classpath/launcher |
| JRE version, CA store, Linux packages | Base/runtime image, PaaS runtime | JVM/application |
| JVM heap, GC, native memory | JVM flags/runtime | Container resource limits |
| HTTP listen port | `server.port` và embedded web server | Docker port publishing, Kubernetes Service |
| Public domain/TLS certificate | Ingress/LB/proxy | Application forwarded-header handling |
| Database URL and secret mount | Platform configuration | Application binding/connection |
| Liveness/readiness semantics | Application/Actuator | Kubelet and Service routing |
| Number of replicas, rollout strategy | Kubernetes controller | App statelessness/compatibility |
| SIGTERM and grace deadline | Container/orchestrator | Boot graceful shutdown |
| Event durability/replay | Application+database/message broker | Restart and rollout policies |
| Image digest/signature/pull | CI/registry/cluster policy | Builder and deploy pipeline |

Một vấn đề có thể vượt nhiều tầng. Ví dụ route public 502 có thể là ingress chọn sai targetPort, pod chưa ready, Tomcat chưa listen hoặc app vừa OOM. Phải quan sát từ client→edge→Service→Pod→JVM thay vì sửa business controller ngay.

### 2.2. Năm khái niệm không thay thế nhau

- **Build artifact**: compiled classes, resources và dependency metadata/JAR.
- **Executable Boot archive**: artifact được plugin repackage, có Boot loader và dependencies để `java -jar` chạy.
- **OCI image**: filesystem layers, runtime/JRE, entrypoint và image metadata để container runtime sử dụng.
- **Container/Pod**: instance đang chạy dưới constraints của OS, namespace, cgroup, env, mounts và network.
- **Deployment/Service/Ingress**: desired state và traffic routing; chúng không phải artifact Java và không tự thay đổi source code.

## 3. Yêu cầu runtime của Spring Boot khác yêu cầu build

Theo tài liệu Spring Boot **4.1.2**, runtime cần tối thiểu **Java 17**; build support cho Maven **3.6.3 trở lên**, Gradle **8.14+ (dòng 8.x)** hoặc **9.x**. Spring Boot còn có yêu cầu Spring Framework/Servlet container tương ứng; với Servlet stack, Tomcat 11 và Jetty 12.1 là các embedded containers được hỗ trợ theo system requirements.

Maven version không nằm trong danh sách bắt buộc của **máy chạy executable JAR**. JRE/JVM tương thích mới là thành phần cần khi dùng `java -jar`. Ngược lại, một server có JDK17 nhưng không cài Maven vẫn chạy được JAR đã build; một build agent có JDK21 nhưng package app target Java17 vẫn cần xác minh dependencies và standard APIs.

### 3.1. Compiler vs runtime JVM

~~~text
CI: JDK 21 + compiler --release 17
                |
                v
Java class file target 17 (major 61)
                |
        +-------+--------+
        |                |
JVM Java 17           JVM Java 21
có thể chạy           thường chạy được
        |
JVM Java 11 -> KHÔNG chạy Java 17 bytecode
~~~

`javac --release 17` khóa cả language level, bytecode và Java standard APIs theo release 17. Chỉ đặt `-source 17 -target 17` trên JDK mới hơn có thể vô tình gọi API Java 21 và phát hiện lỗi khi chạy production.

Tạo một chương trình Java 17 độc lập:

~~~java
public class RuntimeFeature {
    public static void main(String[] args) {
        System.out.println("Target feature: 17");
        System.out.println("Runtime feature: "
                + Runtime.version().feature());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RuntimeFeature.java
java RuntimeFeature
~~~

Khi thực sự dùng JVM 17, stdout:

~~~text
Target feature: 17
Runtime feature: 17
~~~

Trên JVM 21, dòng thứ hai có thể là `Runtime feature: 21`. Ví dụ kiểm JVM đang chạy, không thay Maven compiler target. Khi gặp `UnsupportedClassVersionError`, kiểm **class nào** có bytecode version cao hơn JVM: có thể là dependency chứ không phải main class.

### 3.2. Hợp đồng runtime cần được ghi rõ

| Trường | Ví dụ của một service | Cách kiểm |
| --- | --- | --- |
| Java feature | Java 17+ | `java -version` trong image |
| OS/architecture | Linux AMD64/ARM64 theo image support | Image manifest và node architecture |
| Entrypoint | `java -jar /app/application.jar` | Docker/OCI inspect |
| Inbound port | TCP 8080, listener trên interface của Pod | `server.port`, curl trong namespace |
| Required configuration | Release, region, DB URL, retry timeout | Environment/config validation |
| Sensitive configuration | Credentials, private keys, trust configuration | Secret mount/RBAC/rotation |
| External services | DNS, TLS, DB/broker identity | Connectivity/credentials, application health |
| Resource assumptions | CPU, memory, threads, file descriptors, temp disk | cgroup/limits và load test |
| Startup/health | Startup, live và ready nghĩa gì | Main-port probes |
| Shutdown | SIGTERM, deadline và in-flight policy | Rolling restart/fault testing |
| Durable state | DB/object storage/queue, không giữ tại ephemeral disk | Restart/failover test |

**Java bytecode portable không có nghĩa OCI image portable vô điều kiện.** JNI/native libraries, TLS provider, fonts, OS/ABI, CPU architecture và libc có thể khác giữa AMD64/ARM64 hoặc Linux distributions. GraalVM native binary còn phụ thuộc OS/architecture rõ rệt hơn.

### 3.3. Runtime CPU và memory không chỉ là Java heap

Giả sử Pod memory limit=512Mi. Đặt `-Xmx512m` có thể khiến process bị OOMKilled vì còn Metaspace, code cache, thread stacks, direct buffers, TLS/Netty buffers, native allocations và GC metadata. JVM 17 hiểu một số container limits nhưng phải đo RSS, allocation rate và garbage collection trong giới hạn thật.

Một tùy chọn minh họa:

~~~bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -XX:+ExitOnOutOfMemoryError"
~~~

Con số 60% là điểm thử nghiệm, **không** là preset cho mọi ứng dụng. `JAVA_TOOL_OPTIONS` ảnh hưởng JVM khi launch; không tự đổi JDK binary, compiler target hoặc memory limit mà Kubernetes đặt. Với image Buildpacks, cần chú ý launcher có thể thiết lập `JAVA_TOOL_OPTIONS` của riêng nó; đừng ghi đè cẩu thả.

## 4. Maven/Gradle làm gì trong vòng đời artifact?

Maven/Gradle có thể: resolve dependencies, biên dịch, copy resources, chạy unit/integration tests, tạo JAR/WAR, gọi Boot plugin để repackage hoặc tạo image. Trong production JVM process, Maven/Gradle **không** tự động tiếp tục hoạt động để resolve các dependencies còn thiếu hay inject secrets.

### 4.1. Executable JAR của Spring Boot

Cấu trúc đơn giản:

~~~text
runtime-boundary-lab-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/
│   └── com/example/runtimeboundary/...
├── BOOT-INF/lib/
│   ├── spring-*.jar
│   └── ...
└── org/springframework/boot/loader/...
~~~

Boot Maven plugin mục tiêu `repackage` chuyển một archive thành executable JAR có nested dependencies. Manifest có `Main-Class` trỏ đến Boot launcher và `Start-Class` tới class ứng dụng. Không tự cấu hình Maven jar plugin `Main-Class=com.example.App` rồi kỳ vọng tất cả nested JARs tự load khi chạy với JVM chuẩn.

~~~bash
mvn clean verify
jar tf target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

Nếu gặp `no main manifest attribute` hoặc `ClassNotFoundException`, kiểm artifact có được Boot repackage và có đúng nested libs không; không đưa Maven vào production image như cách chữa.

### 4.2. Những lệnh Maven nói lên điều gì?

| Lệnh | Điều xác minh | Điều **không** xác minh |
| --- | --- | --- |
| `mvn compile` | Source biên dịch được | HTTP listener/TLS, probes |
| `mvn test` | Tests chạy theo build config | Real image/Kubernetes |
| `mvn verify` | Lifecycle tới verify thành công | App sẽ ready trên prod |
| `mvn package` | Tạo artifact | Image đã push |
| `mvn spring-boot:run` | Dev runtime theo classpath/plugin | Executable JAR layout |
| `mvn dependency:tree` | Graph dependencies | Vulnerability policy đã pass |
| `mvn spring-boot:build-image` | Tạo OCI image qua buildpacks | Pod/Service/Ingress đã tồn tại |

Nếu pipeline dùng `-DskipTests`, không được nói mọi tests đã pass chỉ vì package thành công; cần bằng chứng CI thực sự chạy tests ở bước khác.

### 4.3. Gradle và phạm vi tương tự

~~~bash
./gradlew test
./gradlew bootJar
./gradlew bootBuildImage
~~~

`bootJar` của Spring Boot Gradle plugin tạo executable archive; `jar` của Java plugin không luôn có cùng layout/launcher. `bootBuildImage` gọi Cloud Native Buildpacks. Gradle Wrapper/JDK compatibility là vấn đề **build-time**; không suy rằng `gradle` cần được cài trong image runtime nếu image đã chứa executable JAR.

### 4.4. WAR, external servlet container và native image

- Executable JAR thường chạy với embedded Tomcat/Jetty/Netty theo dependencies.
- Một WAR có thể được cấu hình deploy lên **external servlet container**; lúc đó external container kiểm soát servlet version, connector, classloader, TLS, JVM và undeploy. Cần cấu hình packaging/`SpringBootServletInitializer`/dependency scopes phù hợp, không đổi mỗi chữ `jar` thành `war`.
- GraalVM native image là binary biên dịch AOT, **không chạy qua `java -jar`** như JVM archive. Nó cần GraalVM toolchain, native reflection/resource/proxy metadata và test riêng theo OS/architecture.
- Native image không loại trừ nhu cầu runtime config, secrets, probes, DB schema, image signing và graceful shutdown.

## 5. OCI image: Dockerfile và Buildpacks không phải Deployment

**OCI image** có filesystem layers, entrypoint/command, environment metadata và hỗ trợ platform. Một image có thể được Docker chạy local hoặc Kubernetes kéo từ registry. Image không tự tạo Service, hostname public, Secret, database, storage bền hay autoscaler.

### 5.1. Dockerfile làm gì?

- Chọn base image/JRE/OS userspace.
- Copy JAR và resources cần thiết, set working directory.
- Đặt entrypoint, default env, user/permissions.
- Định nghĩa các layers có thể cache, build arguments.
- Cung cấp metadata như `EXPOSE`.

Không dùng Dockerfile để lưu mật khẩu hoặc sản xuất dữ liệu cấu hình khác cho từng môi trường. Đừng dùng floating base tags ở production mà không có rebuild/scan/patch policy.

### 5.2. Cloud Native Buildpacks làm gì?

Cloud Native Buildpacks (CNB) nhận app/JAR cùng builder/buildpacks/run image, tạo image OCI theo lifecycle. Spring Boot có Maven goal:

~~~bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=runtime-boundary-lab:0.0.1
~~~

Goal cần container builder/daemon và quyền kéo builder/run images. `BP_JVM_VERSION` chọn Java version tại **image build time** (theo buildpack hỗ trợ), còn `JAVA_TOOL_OPTIONS` được dùng khi JVM chạy. Buildpack-provided launcher có thể thêm flags/runtime defaults của nó.

| Khía cạnh | Dockerfile | Buildpacks |
| --- | --- | --- |
| Base JRE | Bạn chọn `FROM` | Builder/run image quyết định |
| Image layers | Bạn thiết kế COPY/extract | Buildpacks quản lý |
| Non-root user | Bạn cấu hình | CNB image thiết kế non-root |
| Build | `docker build` | `spring-boot:build-image`/`bootBuildImage` |
| Image registry | Cần push riêng hoặc CI | Cần publish/config credentials |
| Deployment | Không tạo | Không tạo |
| TLS/DB/Secrets/Ingress | Không tự cung cấp | Không tự cung cấp |

Hai cách có thể đóng gói **cùng mã ứng dụng**, nhưng image runtime JRE, CA, libraries, architecture, launch flags có thể khác. Vì vậy phải smoke test cả **image thực tế**, không chỉ build JAR.

### 5.3. EXPOSE khác với port publish

~~~dockerfile
EXPOSE 8080
~~~

`EXPOSE` chủ yếu là image metadata; không đổi `server.port`, không tự mở cổng host hoặc tạo Kubernetes Service. Docker local muốn publish:

~~~bash
docker run --rm -p 127.0.0.1:8080:8080 \
  runtime-boundary-lab:0.0.1
~~~

Vế `127.0.0.1:8080` là **host** bind; `8080` phía phải là **container** port. Spring Boot phải nghe cổng 8080 trên interface có thể kết nối trong container. Nếu Boot chỉ bind `127.0.0.1` **bên trong container**, Docker NAT từ host tới container IP thường không kết nối được.

### 5.4. Image identity và architecture

~~~text
registry.example.test/team/app:prod      # tag có thể mutable
registry.example.test/team/app:1.0.3     # version tag cũng cần policy immutable
registry.example.test/team/app@sha256:... # digest định danh content
~~~

Nên pin digest/immutable tag, lưu build commit, SBOM, provenance, signature, scan results và policies. Khi chạy trên ARM64 nodes, image phải có manifest/platform ARM64 tương thích; Java class files portable không khiến native base image AMD64 tự chạy trên ARM64.

## 6. Configuration là hợp đồng runtime, không phải text replace lúc build

Spring Boot có external configuration qua `application.properties`, YAML, OS env, JVM system properties, command-line switches, `spring.config.import` và config trees. Mục tiêu phổ biến là **build once → deploy same image many times** với config/secret thích hợp cho từng environment.

~~~text
One immutable JAR/image digest
   +-- test:    release=abc123, region=ci
   +-- staging: release=abc123, region=stage
   +-- prod:    release=abc123, region=ap-southeast
          |
          v
Same app version, different runtime settings
~~~

### 6.1. Environment và profile

~~~properties
spring.application.name=runtime-boundary-lab
app.runtime.release=${APP_RELEASE:local}
app.runtime.region=${APP_REGION:dev}
server.port=${PORT:8080}
~~~

Spring property placeholder `${APP_RELEASE:local}` lấy `APP_RELEASE` khi có, dùng `local` nếu không. Cách này giúp Docker/Kubernetes inject env mà **không phải sửa JAR**.

Một cách khác là direct relaxed binding: property `app.runtime.release` thường có thể override bằng OS env `APP_RUNTIME_RELEASE`. Cần chọn **một quy ước**; đừng cho hai cơ chế cạnh tranh rồi không biết cái nào thắng. Spring Boot còn có thứ tự PropertySources: CLI/properties/env/config data/test overrides; không có quy tắc “ENV chắc chắn thắng tất cả”.

`SPRING_PROFILES_ACTIVE=prod` chỉ kích hoạt profile/config được định nghĩa; nó **không** tự tạo TLS, authentication, credentials, connection pools hay network policies.

### 6.2. Secrets không được bake vào JAR/image

Tránh đặt mật khẩu trong:

- `pom.xml`, committed `application-prod.properties`.
- `Dockerfile ENV DB_PASSWORD=...`, build args và image history.
- CI logs/artifact metadata, Maven command line, screenshots.
- Kubernetes ConfigMap public hoặc lệnh in toàn bộ environment của Pod.

Spring Boot hỗ trợ mounted configtree:

~~~properties
# Fragment dành cho ứng dụng thật có DB dependency:
spring.config.import=configtree:/run/secrets/myapp/
spring.datasource.username=${db.username}
spring.datasource.password=${db.password}
~~~

Platform mount file `/run/secrets/myapp/db.username` và `db.password`, rồi Spring import thành configuration properties. Nếu secrets là bắt buộc, cho startup fail-fast khi thiếu; không dùng `optional:` hoặc default giả khiến ứng dụng vô tình chạy sai. Với Kubernetes Secret vẫn cần RBAC, access controls, encryption-at-rest/secret store policies và rotation; không phải cứ dùng object Secret là đã an toàn tuyệt đối.

Đoạn datasource trên **không phải phần chạy trong demo** vì project lab không có database. Thay đổi mounted secret file không có nghĩa mọi đã-bound Spring beans tự reload ngay; có thể cần rolling restart hoặc cơ chế reload cụ thể.

### 6.3. Build config khác runtime config

| Cấu hình | Thời điểm | Chủ thể |
| --- | --- | --- |
| `java.version=17` | Compile/build | Maven compiler |
| `BP_JVM_VERSION` | CNB image build | Buildpacks |
| `JAVA_TOOL_OPTIONS` | JVM startup | JVM/image launcher |
| `SPRING_PROFILES_ACTIVE` | Spring app startup | Spring config loader |
| `PORT`/`server.port` | Spring server runtime | Embedded server |
| `containerPort` | Pod manifest | Kubelet/Service reference |
| `targetPort` | Service routing | Kubernetes networking |
| `terminationGracePeriodSeconds` | Pod lifecycle | Kubelet |
| `EXPOSE` | Image metadata | Dockerfile/image |

Không gán `PORT` rồi mong Kubernetes Service tự đổi theo. Không set `BP_JVM_VERSION` trong Pod rồi mong JRE binary image được thay lập tức. Không set `JAVA_TOOL_OPTIONS` rồi mong đổi `maven.compiler.release`.

## 7. Networking: phải map đúng nhiều tầng cổng

~~~text
Browser: https://shop.example.test:443
           |
           v
Ingress/LB: TLS termination, host/path routing
           |
           v
Kubernetes Service: port 80
           |
           v
Pod targetPort: named http -> 8080
           |
           v
Spring Boot: server.port=8080, listening 0.0.0.0
~~~

- **Ingress/TLS** do nền tảng cấu hình. Public TLS ở edge không bảo đảm backend hop đã mã hóa.
- **Service port** là cổng logic của Service.
- **targetPort** quyết định Pod port được kết nối.
- **containerPort** là khai báo metadata/named port; nó **không bắt** JVM listen.
- **server.port** là setting ứng dụng có tác dụng thực tế với embedded web server.
- **server.address=127.0.0.1** bên trong container chỉ bind loopback; thường sai nếu cần Service routing từ Pod IP.
- **server.address=0.0.0.0** hoặc default phù hợp cho container listener; hạn chế expose bằng policies/ports bên ngoài.

### 7.1. Forwarded headers là trust boundary

Khi Ingress terminate HTTPS và proxy HTTP vào Boot, `request.isSecure()`/scheme, absolute redirects và Secure cookies có thể cần `Forwarded` hoặc `X-Forwarded-*`. `server.forward-headers-strategy=framework`/`native` xử lý forwarded metadata, nhưng **không tự xác minh** chúng có đến từ một proxy đáng tin hay không.

Edge phải strip incoming forwarded headers do client gửi, set headers từ connection thật, dùng Host allowlist và không cho Internet kết nối trực tiếp backend tin header. Test spoofed `X-Forwarded-Host` và `Forwarded: host=...` qua public edge, không chỉ test bằng curl localhost.

### 7.2. Outbound dependencies không dùng localhost tùy tiện

Trong Pod, `localhost:5432` thường là network namespace của **chính Pod**, không phải database trên laptop hay một Pod khác. Runtime config cần DNS managed DB/Kubernetes Service, credentials, CA trust, network policies, retry/backoff và connection pool budgets. Image builder không tạo DB/schema cho bạn; migrations có ownership và rollback policy riêng.

## 8. Lifecycle: startup, readiness, liveness, shutdown

### 8.1. Ba probes hỏi ba câu khác nhau

| Probe | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| Startup | App đã khởi động xong mức cần thiết chưa? | Tránh liveness restart khi warm-up lâu |
| Liveness | App bị kẹt/hỏng nội tại phải restart không? | Kubelet restart khi fail lâu |
| Readiness | App có thể nhận traffic mới không? | Service chọn endpoints |

Với Spring Boot Actuator, `management.endpoint.health.probes.enabled=true` bật groups liveness/readiness; `management.endpoint.health.probes.add-additional-paths=true` cho `/livez`, `/readyz` trên **main application port**. Điều này có giá trị khi management port riêng vẫn sống trong khi main connector đã ngừng nhận requests.

**Không dùng “DB down” làm tiêu chí liveness vô điều kiện:** lỗi DB dùng chung có thể khiến mọi Pods restart đồng loạt và tạo cascading failure. Readiness hoặc circuit breaker phù hợp hơn tùy SLO.

### 8.2. Graceful shutdown nằm ở ranh giới JVM và orchestrator

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring Boot 4.1 hỗ trợ graceful shutdown embedded web server. Nó không thay thế Kubernetes deadline, SIGTERM forwarding hay nghiệp vụ lưu trạng thái bền. Khi dừng, app cần nhận SIGTERM, hạ readiness, hoàn tất finite requests và xử lý những SSE/WebSocket/streaming responses có thể tồn tại rất lâu.

Kubernetes `terminationGracePeriodSeconds` bao gồm thời gian preStop và graceful processing. Nếu preStop sleep 40 giây trong tổng grace 30 giây, Java có thể bị kill trước khi shutdown hooks chạy. SIGKILL không kích hoạt Java hooks.

### 8.3. Entrypoint exec form

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Exec-form giúp container runtime gửi stop signal tới JVM process. Shell-form như sau có thể cản signal forwarding nếu shell không dùng `exec`:

~~~dockerfile
# Không khuyến khích nếu chưa xử lý signal forwarding:
ENTRYPOINT java -jar /app/application.jar
~~~

Timeout phase của Boot **không phải** bảo đảm process luôn thoát trong đúng thời gian đó: còn hooks, blocked I/O, threads, orchestrator deadlines và external shutdown tasks. Đo under-load và test cả SIGTERM lẫn force kill recovery.

## 9. Ví dụ Maven đầy đủ: một ứng dụng, nhiều môi trường

Dự án không dùng database hay cloud account, giúp phân biệt runtime config/packaging. Java code **không biết Docker/Kubernetes**; cùng JAR trả response khác theo env ở runtime.

### 9.1. Cấu trúc

~~~text
runtime-boundary-lab/
  pom.xml
  Dockerfile
  .dockerignore
  src/main/java/com/example/runtimeboundary/
    RuntimeBoundaryApplication.java
    RuntimeContractController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/runtimeboundary/
    RuntimeContractIntegrationTest.java
  k8s/
    deployment.yaml
    service.yaml
~~~

### 9.2. pom.xml

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
    <groupId>com.example</groupId>
    <artifactId>runtime-boundary-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Boot parent quản lý versions; WebMVC starter chứa embedded Tomcat, Boot Actuator cung cấp health/probes, WebMVC test starter cung cấp JUnit/test integration tương thích Boot 4.

### 9.3. RuntimeBoundaryApplication.java

~~~java
package com.example.runtimeboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeBoundaryApplication.class, args);
    }
}
~~~

### 9.4. RuntimeContractController.java

~~~java
package com.example.runtimeboundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeContractController {
    private final String release;
    private final String region;

    public RuntimeContractController(
            @Value("${app.runtime.release}") String release,
            @Value("${app.runtime.region}") String region) {
        this.release = release;
        this.region = region;
    }

    public record RuntimeView(String service, String release, String region) {}

    @GetMapping("/api/runtime")
    public RuntimeView runtime() {
        return new RuntimeView(
                "runtime-boundary-lab", release, region);
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Không trả toàn bộ env/config vào response: có thể chứa tokens, secrets và internal hostnames. Endpoint demo chỉ trả release/region vô hại. Production nên giới hạn access tới diagnostics và dùng Actuator `info` nếu muốn expose build metadata được whitelist.

### 9.5. application.properties

~~~properties
spring.application.name=runtime-boundary-lab

server.port=${PORT:8080}
app.runtime.release=${APP_RELEASE:local}
app.runtime.region=${APP_REGION:dev}

management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
management.endpoints.web.exposure.include=health,info

server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Trong container, không đặt `server.address=127.0.0.1` vì Kubernetes Service/Docker forwarding thường cần app nghe trên interface container. Nếu set đồng thời `PORT` và `SERVER_PORT` với giá trị khác nhau, Spring PropertySources có thể tạo behavior khác kỳ vọng; nên dùng một convention.

### 9.6. RuntimeContractIntegrationTest.java

~~~java
package com.example.runtimeboundary;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "app.runtime.release=ci-123",
        "app.runtime.region=ci",
        "management.endpoint.health.probes.enabled=true",
        "management.endpoint.health.probes.add-additional-paths=true"
    }
)
class RuntimeContractIntegrationTest {
    @LocalServerPort
    int port;

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET().build();

        // Java 17 HttpClient không implement AutoCloseable.
        HttpClient client = HttpClient.newHttpClient();
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void environmentPropertiesReachRealHttpServer() throws Exception {
        HttpResponse<String> response = get("/api/runtime");
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
                "\"release\":\"ci-123\""), response.body());
        assertTrue(response.body().contains(
                "\"region\":\"ci\""), response.body());
    }

    @Test
    void probesUseTheSameApplicationPort() throws Exception {
        assertEquals(200, get("/livez").statusCode());
        assertEquals(200, get("/readyz").statusCode());
    }

    @Test
    void businessEndpointWorks() throws Exception {
        HttpResponse<String> response = get("/api/ping");
        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }
}
~~~

Đây là **test class đầy đủ theo Java 17**. `RANDOM_PORT` khởi tạo embedded server thật, tránh collision CI; `@LocalServerPort` lấy port do server cấp. Test xác nhận HTTP và config trong JVM test process, **không** tự xác minh Docker/Ingress/TLS. Nếu app thực cần khởi tạo các dependency ngoài trước khi ready, thêm test của chúng vào tầng tương ứng.

### 9.7. Build và chạy JAR

~~~bash
java -version
mvn -version
mvn clean verify
java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

Terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -s http://127.0.0.1:8080/api/runtime
curl -i http://127.0.0.1:8080/livez
curl -i http://127.0.0.1:8080/readyz
~~~

Response body của `/api/ping` chính xác là:

~~~text
pong
~~~

Với env không được override, body của `/api/runtime` về mặt dữ liệu là:

~~~json
{"service":"runtime-boundary-lab","release":"local","region":"dev"}
~~~

JSON property order/headers có thể khác, nhưng ba field values được code xác định. Health endpoints thường trả 200 sau khi app ready; headers/JSON health components tùy cấu hình.

### 9.8. Chạy cùng JAR ở port và config khác

Bash/POSIX:

~~~bash
APP_RELEASE=release-42 APP_REGION=staging PORT=8081 \
  java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

Gọi:

~~~bash
curl -s http://127.0.0.1:8081/api/runtime
~~~

Body dự kiến:

~~~json
{"service":"runtime-boundary-lab","release":"release-42","region":"staging"}
~~~

PowerShell:

~~~powershell
$env:APP_RELEASE = "release-42"
$env:APP_REGION = "staging"
$env:PORT = "8081"
java -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

Không cần rebuild JAR để đổi port/region, nhưng platform routing và probes cũng phải map theo port mới. Không chạy hai tiến trình cùng listen 8080/8081 mà quên stop tiến trình trước.

## 10. Dockerfile runtime-only: build một lần rồi chạy

### 10.1. Dockerfile

~~~dockerfile
# Production nên pin image bằng digest và cập nhật patch có kiểm soát.
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY --chown=10001:10001 \
  target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar \
  /app/application.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

Dockerfile copy JAR đã đóng gói, không mang Maven/compiler vào runtime container. Sử dụng numeric non-root UID; các files cần đọc/ghi phải có quyền tương ứng. Base image tag là mutable trong thực tế; production pin digest, scan và rebuild khi có CVE/Java patches.

### 10.2. .dockerignore

~~~text
.git
.idea
.vscode
src
k8s
tls
secrets
.env
.env.*
target/*
!target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar
~~~

Các rules phù hợp Dockerfile chỉ COPY artifact đã build. Nếu chuyển sang multi-stage Dockerfile build source, điều chỉnh ignore để builder đọc được POM/src. Không gửi keys, .env hay Git history vào build context nếu không cần.

### 10.3. Build image và chạy

Sau `mvn clean verify`:

~~~bash
docker build -t runtime-boundary-lab:0.0.1 .

docker run --rm --name runtime-boundary-lab \
  -p 127.0.0.1:8080:8080 \
  -e PORT=8080 \
  -e APP_RELEASE=image-001 \
  -e APP_REGION=container-lab \
  --memory=512m --cpus=1 \
  runtime-boundary-lab:0.0.1
~~~

Terminal khác:

~~~bash
curl -s http://127.0.0.1:8080/api/runtime
curl -i http://127.0.0.1:8080/readyz
docker logs runtime-boundary-lab
~~~

Body dự kiến từ `/api/runtime`:

~~~json
{"service":"runtime-boundary-lab","release":"image-001","region":"container-lab"}
~~~

Nếu kết nối bị từ chối, kiểm process Java có đang listen 8080, `server.address` có bind phù hợp, `-p` đúng và port host đã được dùng chưa. Đừng suy từ dòng `EXPOSE 8080` rằng network đã tự hoạt động.

### 10.4. Observability và stop signal trong container

~~~bash
docker image inspect runtime-boundary-lab:0.0.1
docker inspect runtime-boundary-lab
docker logs runtime-boundary-lab
docker stats runtime-boundary-lab
docker stop --time 30 runtime-boundary-lab
~~~

`docker stop` gửi stop signal cho PID1 rồi kill sau timeout nếu chưa thoát. `--time 30` là Docker timeout của lệnh, khác với `spring.lifecycle.timeout-per-shutdown-phase=20s`. Nếu API còn SSE/WebSocket/large requests, app có thể cần logic drain trước SIGTERM. Không claim process luôn thoát trong 20 giây.

### 10.5. Layered JAR và tối ưu image

Spring Boot có layered archive và tools jarmode:

~~~bash
java -Djarmode=tools \
  -jar target/runtime-boundary-lab-0.0.1-SNAPSHOT.jar \
  list-layers
~~~

Boot metadata có thể chia `dependencies`, `spring-boot-loader`, `snapshot-dependencies` và `application`; tối ưu Docker cache khi source thay đổi mà dependencies ít thay. Đây là tối ưu **image build/pull**, không làm một API runtime tự chính xác hơn.

Boot phiên bản mới dùng `-Djarmode=tools` theo tài liệu hiện hành, nên không sao chép vô điều kiện lệnh `layertools` của hướng dẫn cũ.

## 11. Buildpacks: cách tạo image khác, hợp đồng app giống

~~~bash
mvn spring-boot:build-image \
  -Dspring-boot.build-image.imageName=runtime-boundary-lab:0.0.1
~~~

Goal sử dụng builder/run image và buildpacks để tạo OCI image, không cần Dockerfile. Docker-compatible daemon/permissions thường cần khi chạy plugin. Spring Boot plugin có thể suy Java version mục tiêu từ compiler configuration; có thể dùng `BP_JVM_VERSION` ở builder nếu muốn override có kiểm soát.

Sau buildpack image, **vẫn phải test runtime image**:

~~~bash
docker run --rm -p 127.0.0.1:8080:8080 \
  -e APP_RELEASE=buildpack-001 \
  -e APP_REGION=container-lab \
  runtime-boundary-lab:0.0.1
~~~

Không phải mọi builder/runtime image có cùng JVM flags, CA, user/entrypoint hoặc layer layout như Dockerfile; kiểm image inspect/health trong môi trường thật. Buildpacks **không** tự tạo Kubernetes Service/Ingress, registry credentials, signed digest, required secrets hay database migrations.

## 12. Kubernetes hiện thực runtime contract: Deployment và Service

Manifests sau là **cấu trúc tham khảo**. Image `registry.example.test/team/runtime-boundary-lab:0.0.1` là tên ví dụ, cần build/push sang registry thật và cấp quyền imagePull trước khi áp dụng. Không có public Ingress/TLS vì phải tùy hạ tầng và chứng thư.

### 12.1. k8s/deployment.yaml

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: runtime-boundary-lab
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: runtime-boundary-lab
  template:
    metadata:
      labels:
        app: runtime-boundary-lab
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.test/team/runtime-boundary-lab:0.0.1
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          env:
            - name: PORT
              value: "8080"
            - name: APP_RELEASE
              value: "release-0.0.1"
            - name: APP_REGION
              value: "cluster-lab"
          startupProbe:
            httpGet:
              path: /livez
              port: http
            failureThreshold: 30
            periodSeconds: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            failureThreshold: 2
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
          volumeMounts:
            - name: temp
              mountPath: /tmp
      volumes:
        - name: temp
          emptyDir: {}
~~~

Giải thích:

- `replicas` và rolling strategy thuộc platform; ứng dụng phải đủ stateless/backward compatible để chạy nhiều instances.
- `PORT=8080` → Spring placeholder → listen 8080, khớp named container port `http`.
- `startupProbe` tránh liveness kill trong warm-up; `readinessProbe` quyết định nhận traffic; `livenessProbe` quyết định restart.
- CPU/memory là cgroup/runtime constraints, không phải POM compiler settings.
- `runAsNonRoot`/read-only filesystem là hardening; `emptyDir` tại `/tmp` cho file tạm JVM/Tomcat. Dữ liệu trong emptyDir không bền sau Pod xóa.
- `terminationGracePeriodSeconds:45` là tổng deadline, bao gồm preStop nếu thêm; phải phù hợp app drain/hook thực.
- Tag image dùng cho demo; production nên pin digest/immutability và signature policies.

### 12.2. k8s/service.yaml

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: runtime-boundary-lab
spec:
  selector:
    app: runtime-boundary-lab
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  type: ClusterIP
~~~

`port 80` của Service route tới named container port `http=8080`. Service không tự cấp public TLS/DNS. Cần Ingress/Gateway/LoadBalancer và network/security policies phù hợp nếu cần client từ Internet.

### 12.3. Lệnh triển khai khi đã có registry/cluster

~~~bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl rollout status deployment/runtime-boundary-lab
kubectl get pods -l app=runtime-boundary-lab
kubectl describe deployment runtime-boundary-lab
kubectl logs deployment/runtime-boundary-lab
~~~

Để smoke test từ máy quản trị:

~~~bash
kubectl port-forward service/runtime-boundary-lab 8080:80
~~~

Terminal khác:

~~~bash
curl -s http://127.0.0.1:8080/api/runtime
curl -i http://127.0.0.1:8080/readyz
~~~

Port-forward không chứng minh public Ingress/TLS đã hoạt động; nó chỉ tạo đường kết nối qua API server và Service-selected Pod để kiểm nội bộ. Pod RUNNING cũng chưa có nghĩa READY; xem endpoints/probes/events.

### 12.4. Các lỗi platform thường gặp

- `ImagePullBackOff`: sai image ref/digest, registry credentials/IAM, không truy cập registry hoặc architecture không phù hợp.
- `CrashLoopBackOff`: process liên tục exit hoặc liveness restart; xem previous logs/exit reason.
- `OOMKilled`: cgroup memory limit bị vượt, kể cả native memory ngoài Java heap.
- `Readiness probe failed`: sai path/port, app chưa ready, DB/feature dependency, resource pressure.
- `Connection refused` qua Service: app bind 127.0.0.1 trong Pod, lắng nghe sai port hoặc endpoints chưa có.
- HTTP 502/503 từ Ingress: backend pods không ready, routing/timeout/TLS upstream, ingress rules sai.
- SIGTERM nhưng shutdown lâu: process không nhận signal, streams không kết thúc, grace không đủ.
- Rolling deploy không chuyển traffic: selector/Service labels sai, new Pods chưa ready hoặc external LB propagation.

## 13. Build once, deploy many và supply chain

Một pipeline mẫu:

~~~text
Source commit/tag
  -> dependency resolution + compile/tests
  -> Maven executable JAR
  -> JAR smoke test
  -> OCI image build
  -> image smoke test + SBOM/CVE scans
  -> sign image / record immutable digest
  -> push into trusted registry
  -> stage deploy by SAME digest
  -> Service/Ingress/probe and business smoke tests
  -> promote SAME digest into production
  -> rolling/canary rollout, monitoring, rollback policy
~~~

**Build once** giúp cùng bytes đã test chuyển qua các môi trường, chỉ đổi runtime config/secrets. Nếu CI rebuild riêng cho staging/prod bằng passwords/URLs và tạo artifacts khác nhau, mỗi môi trường đã có một release riêng chưa có cùng bằng chứng test.

### 13.1. SBOM, digest và provenance khác nhau

- **SBOM:** danh sách thành phần/dependencies/versions, hỗ trợ kiểm tra license/CVE.
- **Digest:** định danh nội dung image, chống drift của mutable tags.
- **Signature/attestation:** liên kết image với nhà phát hành và build workflow.
- **Provenance:** ghi commit, builder, build parameters và nguồn artifact.
- **Vulnerability scan:** cảnh báo các thư viện/JRE/OS CVEs theo policy.

Một image đã scan hôm nay không tự cập nhật JRE ngày mai; phải rebuild, test và rollout. Ký image không bảo đảm business code đúng, chỉ giúp tin nguồn/chuỗi phân phối theo trust policy.

### 13.2. Rollback không chỉ đổi tag

Nếu release mới đã thay DB schema không tương thích hoặc format event, quay image cũ có thể phá dữ liệu. Thiết kế migration kiểu expand-contract, backward/forward compatible clients/consumers, idempotency/replay và rollback rehearsal. Không xem local container filesystem là nguồn sự thật bền cho dữ liệu nghiệp vụ.

## 14. Troubleshooting theo từng tầng

| Lỗi | Tầng cần điều tra đầu tiên | Hành động |
| --- | --- | --- |
| Maven resolve deps fail | Build/repository | POM, repository credentials/network |
| Compiler JDK thiếu API | Build/JDK target | `--release`, toolchains, dependencies |
| `UnsupportedClassVersionError` | Runtime JVM | Java version trong image và class version |
| `no main manifest attribute` | Packaging | Boot repackage, đúng JAR |
| `ClassNotFoundException` | Archive/classpath | BOOT-INF/lib, exclusions |
| Docker COPY JAR fail | Build context | `mvn package`, .dockerignore, path |
| `exec format error` | Image architecture | linux/amd64 vs arm64/native binary |
| Permission denied | Image user/FS | Numeric UID/GID, COPY permissions, volumes |
| `ImagePullBackOff` | Registry/cluster | Pull secret, image digest/tag, network |
| `CrashLoopBackOff` | Runtime/health | Logs --previous, exit code, liveness |
| Address already in use | Runtime connector | server.port và các processes |
| Service trả connection refused | Networking | targetPort, app bind address, Pod endpoints |
| Pod RUNNING NotReady | Health/lifecycle | readiness, startupProbe, dependencies |
| `OOMKilled` | Runtime resources | Heap+offheap RSS vs memory limits |
| Redirect host/scheme sai | Edge/proxy | Forwarded headers/Host allowlist |
| Public TLS cert mismatch | Ingress/PKI | SNI, SAN, trust chain |
| 503 khi deploy | Rolling/readiness/proxy | New Pod ready, disruption budget, drain |
| Mất data khi pod restart | Stateful design | External durable DB/storage/replay |

### 14.1. Tình huống sai port

CI package pass, image build pass, app chạy trong Pod và log “Started”. Nhưng Deployment có `PORT=9090`, `containerPort:8080`, Service `targetPort:http` trỏ 8080. Kết quả: Java listen 9090 trong khi Service/probes đi 8080. **Sửa hợp đồng port**, không sửa controller hay Maven plugin.

### 14.2. OOMKilled dù -Xmx nhỏ hơn limit

Heap là một phần của RSS. Có thread stacks, metaspace, direct buffers, native libraries, mmap và GC. Kiểm cgroup memory counters, JVM flags, GC/RSS, offheap pools, Netty/Tomcat buffers, requests in flight; giảm queue/payload hoặc tăng limit theo capacity trước khi chỉ nâng heap.

### 14.3. Liveness restart storm khi DB down

Nếu liveness phụ thuộc database bên ngoài, sự cố DB làm tất cả Pods restart và dồn thêm connections lên DB khi phục hồi. Thiết kế liveness theo trạng thái nội tại, readiness theo khả năng nhận traffic và có circuit breaker/retry. Không sửa bằng cách tắt mọi probes.

### 14.4. Same digest nhưng staging pass, production fail

So sánh config/secret references, DNS, CA/truststore, architecture, container limits, node policies, Ingress, database migrations, clock/timezone, outbound egress. Cùng image bảo đảm artifact identity, **không** đảm bảo các môi trường giống nhau.

## 15. Ma trận kiểm thử release contract

| Phép thử | Ở đâu? | Kết quả mong đợi |
| --- | --- | --- |
| Compile Java17 | CI | Không dùng APIs/bytecode quá mới |
| Executable manifest | CI | `java -jar` start được |
| HTTP real port | JUnit RANDOM_PORT | /api/runtime và /api/ping đúng |
| Env override | JAR runtime | APP_RELEASE/APP_REGION đổi response |
| Port override | JAR runtime | PORT=8081 listen 8081 |
| Image smoke | Docker | JRE đúng, non-root, health pass |
| Image architecture | Registry/cluster | Image chạy trên target nodes |
| Image pull | Kubernetes | Pull thành công bằng credentials/policy |
| Service routing | K8s | /readyz qua targetPort đúng |
| Startup/liveness/readiness | K8s | Khác semantics, không restart storm |
| Secrets | Staging | Missing required secret fail-fast |
| TLS/Ingress | Staging | CA/SAN/SNI/redirect/headers đúng |
| CPU/memory | Load test | Không OOM, p99/GC trong SLO |
| SIGTERM | Docker/K8s | Signal tới JVM, shutdown bounded |
| Rollout/rollback | Staging | Capacity và schema compatibility giữ |
| Durable data | Chaos test | Restart không mất events/transactions |

**Negative tests quan trọng:** chạy với JVM cũ, bỏ secret, đặt port lệch, container filesystem read-only, image wrong architecture, TLS hostname mismatch, forged forwarded host, CPU throttling, OOM, readiness REFUSING_TRAFFIC, SIGKILL lúc đang xử lý và DB tạm mất kết nối.

Các test này không phải tất cả đều nằm trong `mvn test`: JUnit lab chỉ kiểm Java/Spring server thật; platform tests đòi image, registry, ingress, DNS, TLS và cluster.

## 16. Sai lầm phổ biến

| Hiểu lầm | Sửa cách hiểu |
| --- | --- |
| “Production phải cài Maven” | Runtime cần JRE và artifact/classpath phù hợp |
| “Maven package pass nghĩa là Docker image đã sẵn sàng” | Build artifact và build image là hai bước khác |
| “Image build pass nghĩa là Service chạy” | Còn image pull, Pod, probes, routing |
| “EXPOSE là public port” | Chỉ metadata; Docker -p/K8s Service route riêng |
| “containerPort điều chỉnh server.port” | Không, phải đồng bộ hai config |
| “Docker image = Deployment” | Một bên artifact, bên kia controller desired state |
| “Cứ dùng prod profile là có security” | Profile không thay auth, TLS và secret policies |
| “Secrets nên được bake vào JAR cho tiện” | Không, inject runtime và bảo vệ quyền |
| “Tag latest là artifact identity cố định” | Dùng immutable tags/digest |
| “Maven target Java17 nghĩa image JRE17” | Build và runtime JVM là hai hợp đồng |
| “Java17 bytecode chạy trên Java11” | JVM từ chối class version mới |
| “K8s Service tự nhận ra app port” | targetPort/port vẫn phải đúng |
| “Pod Running = Ready” | Health/availability có semantics riêng |
| “DB down thì liveness fail” | Gây restart storm, cần cân nhắc readiness |
| “-Xmx = memory limit an toàn” | Còn native/off-heap memory |
| “TLS tại ingress cũng mã hóa hop nội bộ” | Tùy backend TLS/network policy |
| “HTTP2 tại browser nghĩa Tomcat backend h2” | Edge có thể h2→h1 |
| “SIGTERM luôn cho đủ thời gian” | Phụ thuộc entrypoint/grace/hook/stream |
| “Native image chỉ là đổi jar thành exe” | Cần AOT/native build và compatibility testing |
| “Rollback image cũ là rollback xong” | DB/data/events/config compatibility còn quan trọng |

## 17. Checklist triển khai production

### Artifact và build

- [ ] Toolchain Java17+ đúng, dependency versions/CVEs được quản lý.
- [ ] Tests chạy trước packaging; JAR executable manifest/nested deps được kiểm.
- [ ] `java -jar` smoke test bằng JVM image/runtime thực tế.
- [ ] Buildpacks/Dockerfile có base JRE, architecture và provenance đúng.
- [ ] Không đưa secrets hoặc .env vào artifact/image.

### Image và supply chain

- [ ] Non-root user, permissions, writable temp rõ ràng.
- [ ] JRE patch và base digest có lifecycle cập nhật.
- [ ] SBOM, CVE scan, signature và immutable image digest.
- [ ] Image smoke test thành công trước registry/deploy.
- [ ] Entrypoint exec-form forward SIGTERM đúng.
- [ ] Không giả định EXPOSE mở firewall hoặc Service.

### Runtime config và networking

- [ ] `server.port` khớp containerPort/targetPort/probes.
- [ ] App container không bind loopback nếu cần Service inbound.
- [ ] Required config/secrets được inject đúng names và fail-fast khi thiếu.
- [ ] Env/profile/ConfigMap/Secret precedence, reload behavior được hiểu.
- [ ] Database DNS/TLS/credentials/network permissions hợp lệ.
- [ ] Ingress TLS/forwarded headers/redirect/Host allowlist được test.
- [ ] Không có endpoints Actuator nhạy cảm public, logs không chứa secrets.

### Kubernetes/lifecycle

- [ ] Startup/live/ready probes đúng trách nhiệm và port chính.
- [ ] CPU/memory requests/limits đã load test, heap/offheap có headroom.
- [ ] Rolling strategy có healthy capacity, PodDisruptionBudget khi cần.
- [ ] SIGTERM, preStop và shutdown grace có deadline nhất quán.
- [ ] Durable state không dựa vào container local ephemeral filesystem.
- [ ] Image rollout/rollback có smoke tests, schema compatibility và metrics.
- [ ] Có runbook cho ImagePullBackOff, OOMKilled, NotReady và proxy 502.

## 18. Câu hỏi tự kiểm tra kèm đáp án

**1.** Maven tạo executable JAR thì production có cần Maven không?

**Đáp án:** Không. Với JRE đúng version và archive đóng gói đầy đủ, `java -jar` đủ khởi động ứng dụng.

**2.** Buildpacks có tự tạo Kubernetes Service và database không?

**Đáp án:** Không. Buildpacks tạo OCI image; platform/manifest/service owner lo routing, secrets và external dependencies.

**3.** `server.port=9090` nhưng Service targetPort=8080 thì lỗi ở đâu?

**Đáp án:** Hợp đồng giữa runtime listener và platform routing không khớp. Sửa config/Service, không sửa business controller.

**4.** Có phải Docker `EXPOSE 8080` làm browser ngoài Internet truy cập được không?

**Đáp án:** Không. Phải có port publishing/network access/Ingress phù hợp; EXPOSE chỉ metadata.

**5.** Vì sao cùng JAR vẫn cần smoke test image?

**Đáp án:** Runtime JRE, CA, OS libraries, architecture, permissions, entrypoint, JVM flags có thể khác build machine.

**6.** Vì sao dùng `--release 17` tốt hơn chỉ source/target 17?

**Đáp án:** Nó còn giới hạn Java standard API theo Java17 để tránh dùng API của Java version mới khi compile bằng JDK mới.

**7.** `SPRING_PROFILES_ACTIVE=prod` có tự bảo vệ secrets/TLS không?

**Đáp án:** Không. Profile chọn config đã định nghĩa; security và secrets cần được thiết kế/cấp riêng.

**8.** Có nên dùng database connectivity trong liveness vô điều kiện?

**Đáp án:** Không. DB lỗi chung có thể khiến pods restart hàng loạt; readiness/health groups/circuit breaker cần thiết kế theo recovery semantics.

**9.** Vì sao `-Xmx512m` có thể OOMKilled trong Pod memory limit 512Mi?

**Đáp án:** JVM còn metaspace, native/direct memory, stacks, GC metadata và buffers ngoài heap; cgroup tính tổng memory.

**10.** Kubernetes Secret cập nhật thì ứng dụng luôn nhận giá trị mới ngay?

**Đáp án:** Không. Env trong process không đổi; mounted files có thể cập nhật nhưng đã-bound beans không nhất thiết reload. Cần lifecycle/rotation policy.

**11.** Một pod RUNNING nhưng không READY có phải source compile lỗi?

**Đáp án:** Không nhất thiết. Kiểm probes, port, startup, dependency, CPU/RAM, config và platform routing.

**12.** Public HTTPS có nghĩa backend Pod đang dùng TLS không?

**Đáp án:** Không. Ingress có thể terminate HTTPS rồi proxy HTTP/1.1; internal hop cần bảo vệ theo threat model.

**13.** Digest và image tag khác nhau như thế nào?

**Đáp án:** Digest định danh content; tag có thể trỏ đến digest khác nếu registry cho phép ghi đè. Deploy bằng digest/immutable tags giảm drift.

**14.** Rollback Docker image cũ có chắc an toàn không?

**Đáp án:** Không. DB schema, event formats và runtime config có thể đã thay đổi. Cần migration/compatibility/rollback tests.

**15.** Spring Boot 4.1.2 yêu cầu Java tối thiểu bao nhiêu?

**Đáp án:** Java 17, nhưng dependencies khác trong app có thể nâng minimum thực tế.

## 19. Tài liệu chính thức

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).
- [Spring Boot — Installing and Running](https://docs.spring.io/spring-boot/installing.html).
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html).
- [Spring Boot Maven Plugin — Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html).
- [Spring Boot — OCI Images with Cloud Native Buildpacks](https://docs.spring.io/spring-boot/maven-plugin/build-image.html).
- [Spring Boot — Dockerfiles and Layering](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html).
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html).
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).
- [Spring Boot — Deploying to the Cloud](https://docs.spring.io/spring-boot/how-to/deployment/cloud.html).
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/).
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).
- [Kubernetes — Services and Networking](https://kubernetes.io/docs/concepts/services-networking/service/).
- [Kubernetes — Liveness/Readiness/Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/).
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).
- [Kubernetes — Managing Container Resources](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [OCI Image Specification](https://github.com/opencontainers/image-spec).
- [Cloud Native Buildpacks — Concepts](https://buildpacks.io/docs/for-platform-operators/concepts/).
- [OWASP — Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html).

**Kết luận:** Maven/Gradle tạo **artifact**, Dockerfile/Buildpacks tạo **runtime image**, platform tạo **môi trường, traffic routing, replicas, resources và lifecycle**, còn JVM + Spring Boot thực thi ứng dụng. Kiến thức triển khai cần bắt đầu từ **runtime contract**: Java 17+, classpath, settings/secrets, port, probes, TLS/proxy, CPU/RAM, shutdown và durable state. Hãy **build một lần, test artifact và image riêng, promote bằng digest, đo trong môi trường triển khai thật**, rồi mới kết luận release có thể hoạt động ổn định.