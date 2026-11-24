# Dựng CI với kiểm thử JVM, AOT, native và kiểm chứng container cuối cùng

## 1. Mục tiêu của bài thực hành

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng Spring AOT và biên dịch thành GraalVM Native Image để cải thiện thời gian khởi động, mức sử dụng bộ nhớ và cách đóng gói. Một pipeline chỉ chạy unit test trên JVM chưa chứng minh executable native có thể khởi động, xử lý nghiệp vụ hoặc chạy đúng trong container sẽ được phát hành.

Bài thực hành này xây dựng một pipeline có các cổng kiểm tra nối tiếp:

1. Kiểm thử JVM để xác nhận logic ứng dụng và hợp đồng API cơ bản.
2. Chạy Spring AOT để phát hiện điều kiện cấu hình và generated code không hợp lệ.
3. Biên dịch Native Image để phát hiện vấn đề reachability, reflection, resource và native toolchain.
4. Chạy native tests để kiểm tra các Spring test context trong môi trường native.
5. Đóng gói executable vào container runtime cuối.
6. Khởi chạy đúng image đó, kiểm tra readiness, API, quyền chạy và shutdown.

Kết quả CI cần là một image đã được kiểm thử. Image được publish/deploy theo digest đã kiểm chứng, không build lại một image khác sau khi test.

## 2. Kiến trúc pipeline

~~~mermaid
flowchart TD
    A["Checkout source + pinned toolchain"] --> B["JVM unit / integration tests"]
    B -->|Pass| C["Spring AOT processing"]
    C -->|Pass| C2["AOT mode JVM smoke"]
    C2 -->|Pass| D["Native executable compilation"]
    D -->|Pass| E["Native tests"]
    E -->|Pass| F["Package exact native binary"]
    F --> G["Build final OCI image"]
    G --> H["Inspect image and binary"]
    H --> I["Run final container"]
    I --> J["Readiness + API smoke + dependency checks"]
    J --> K["Graceful shutdown + digest"]
    K --> L["Publish / deploy tested digest"]
~~~

Mỗi bước xác nhận một nhóm rủi ro khác nhau:

| Cổng | Câu hỏi cần trả lời | Ví dụ lỗi được phát hiện |
| --- | --- | --- |
| JVM tests | Logic và contract có đúng không? | Nghiệp vụ sai, validation sai, regression |
| AOT | ApplicationContext có thể được phân tích ở build time không? | Condition phụ thuộc môi trường, bean không được nhận diện, generated initializer lỗi |
| Native compile | GraalVM có thể tạo executable không? | Thiếu reachability metadata, resource, JNI/proxy metadata, toolchain |
| Native tests | Các test context quan trọng có chạy được trong native mode không? | Reflection/serialization/proxy lỗi khi chạy native |
| Container build | Binary có được đóng gói với runtime dependencies phù hợp không? | Thiếu loader, shared library, CA certificate hoặc file cấu hình |
| Container verification | Image cuối có thực sự phục vụ được request không? | Port, permission, health, DNS/TLS, signal/shutdown hoặc cấu hình runtime |

Không gộp tất cả thành một lệnh build duy nhất rồi chỉ kiểm tra exit code. Log và artifact của từng cổng giúp xác định lỗi xuất hiện ở lớp nào.

## 3. Chuẩn bị ứng dụng mẫu

Giả sử dự án là dịch vụ billing có:

- REST API tạo và tra cứu hóa đơn;
- validation request và error handling;
- gọi một partner API qua HTTP client;
- truy cập database;
- Actuator health endpoint;
- cấu hình logging và metrics;
- một số thư viện cần reflection hoặc resource hints.

Tên executable trong ví dụ là **billing-service** và cổng HTTP là **8080**. Thay endpoint, dependency, profile và tên artifact theo ứng dụng thật.

### 3.1. Bật readiness và liveness

Nếu ứng dụng dùng Spring Boot Actuator, bật health probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Khi Actuator được đưa vào dependency và endpoint health được expose theo cấu hình của dự án, Spring Boot cung cấp readiness và liveness groups. CI có thể gọi:

~~~text
GET /actuator/health/readiness
GET /actuator/health/liveness
~~~

Readiness trả trạng thái cho biết instance đã sẵn sàng nhận traffic. Liveness giúp xác định process còn hoạt động. Không đưa mọi external dependency vào liveness check; database hoặc partner API tạm thời lỗi không nên khiến orchestrator liên tục restart mọi instance.

Nếu không dùng Actuator, cung cấp health/readiness endpoint tương đương và thay URL trong workflow.

### 3.2. Cố định cấu hình build time

Spring AOT chuẩn bị ApplicationContext ở build time. Các điều kiện như profile, property và classpath có thể được đánh giá trước khi executable chạy.

Ghi lại:

- Spring profile được dùng khi AOT processing;
- property làm thay đổi bean conditions;
- JDK/GraalVM version;
- Spring Boot và Native Build Tools version;
- native-image arguments;
- OS, CPU architecture và libc của môi trường build;
- các resource/hints do ứng dụng và dependency cung cấp.

Không để CI build AOT bằng một profile nhưng container chạy profile khác nếu hai profile làm thay đổi bean graph. Các cấu hình thuần runtime như port, endpoint, secret và connection string nên được truyền qua environment hoặc secret store khi container chạy.

## 4. Cấu hình build tool

Chọn một build tool cho mỗi pipeline run. Không chạy cả Maven và Gradle trên cùng source trong cùng một job nếu dự án chỉ duy trì một build definition.

### 4.1. Gradle

Áp dụng Spring Boot plugin và GraalVM Native Build Tools plugin:

~~~kotlin
plugins {
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-version>"
    id("org.graalvm.buildtools.native") version "<native-build-tools-version>"
}

graalvmNative {
    binaries {
        named("main") {
            imageName.set("billing-service")
        }
    }
}

tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveFileName.set("billing-service.jar")
}
~~~

Thay placeholder bằng các version đã pin trong dự án. Spring Boot Gradle plugin tự cấu hình các task AOT khi GraalVM Native Image plugin được áp dụng.

Các task chính:

~~~bash
./gradlew test
./gradlew processAot
./gradlew nativeCompile
./gradlew nativeTest
~~~

- **test:** chạy test JVM.
- **processAot:** chạy Spring AOT cho application context.
- **nativeCompile:** tạo native executable; task sử dụng output AOT và reachability metadata theo cấu hình plugin.
- **nativeTest:** xử lý và chạy các test Spring TestContext được hỗ trợ trong native mode.

Với cấu hình tên binary ở trên, executable thường nằm tại:

~~~text
build/native/nativeCompile/billing-service
~~~

Xác nhận đường dẫn bằng output task của Gradle; multi-module project có thể có thư mục output khác theo module.

### 4.2. Maven

Nếu dùng Spring Boot Starter Parent, thêm hai plugin vào module ứng dụng:

~~~xml
<build>
    <finalName>billing-service</finalName>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
            <configuration>
                <imageName>billing-service</imageName>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Starter Parent cung cấp profile **native** để cấu hình Spring AOT và Native Build Tools, đồng thời profile **nativeTest** để xử lý test AOT và chạy native tests.

Các lệnh chính:

~~~bash
./mvnw -B clean verify
./mvnw -B -Pnative spring-boot:process-aot
./mvnw -B -Pnative native:compile
./mvnw -B -PnativeTest test
~~~

Executable thường nằm trong thư mục target của module, theo image name được cấu hình cho Native Build Tools.

Nếu không dùng Starter Parent, cần tự cấu hình các execution tương ứng, tối thiểu gồm Spring Boot plugin goals cho application/test AOT và Native Build Tools goals cho native compilation/test. Không giả định profile **native** hoặc **nativeTest** tồn tại khi dự án không kế thừa Parent.

### 4.3. Chọn đúng bộ version

Không lấy version JDK, Spring Boot, GraalVM và Native Build Tools độc lập từ nhiều ví dụ khác nhau. Kiểm tra ma trận tương thích và pin:

| Thành phần | Điều cần pin |
| --- | --- |
| Java | Major version, vendor và patch/update policy |
| Spring Boot | Version quản lý Spring Framework và plugin |
| GraalVM | Distribution, JDK version và Native Image version |
| Native Build Tools | Maven/Gradle plugin version tương thích |
| OS/architecture | Runner image và target image |
| Native dependencies | Compiler, libc baseline và thư viện hệ thống |

Nếu nâng một thành phần, chạy lại toàn bộ native pipeline và cập nhật artifact provenance.

## 5. Cổng 1 — kiểm thử JVM

Chạy test JVM trước vì đây là vòng phản hồi nhanh nhất:

Gradle:

~~~bash
./gradlew clean test
~~~

Maven:

~~~bash
./mvnw -B clean verify
~~~

Tổ chức test theo mục đích:

| Nhóm test | Phạm vi |
| --- | --- |
| Unit test | Service, mapper, validation và logic nghiệp vụ |
| Web slice | Controller, serialization và error response |
| Data slice | Repository, query và mapping |
| Integration test | Database, HTTP client, message broker và external adapter |
| Contract test | Request/response, status code và schema API |

Test JVM không thay thế native test. Tuy vậy, không nên chuyển mọi unit test sang native vì native test có thời gian biên dịch và giới hạn framework riêng. Giữ test JVM rộng, rồi chọn một tập test có Spring TestContext và các luồng rủi ro cao để chạy native.

Lưu test report và làm pipeline thất bại khi có test failure. Không chạy AOT/native build nếu cổng JVM đã thất bại.

## 6. Cổng 2 — Spring AOT

### 6.1. Chạy AOT riêng

Gradle:

~~~bash
./gradlew processAot
~~~

Maven:

~~~bash
./mvnw -B -Pnative spring-boot:process-aot
~~~

Mục tiêu của cổng này là phát hiện lỗi trong quá trình phân tích ApplicationContext trước khi Native Image compilation bắt đầu.

### 6.2. Kiểm tra output AOT

Sau khi task hoàn thành, xem generated output trong build directory của module. Xác nhận:

- AOT processing kết thúc thành công;
- generated initializer và generated source được tạo;
- bean conditions phản ánh profile/property build time;
- custom RuntimeHintsRegistrar đã được Spring AOT phát hiện;
- resource và proxy hints được đưa vào output;
- không có class hoặc dependency bị loại khỏi classpath.

Không sửa trực tiếp file generated trong build directory. Sửa source configuration, bean declaration, RuntimeHintsRegistrar hoặc dependency rồi chạy AOT lại.

### 6.3. Kiểm tra build-time conditions

Giả sử production dùng profile production để tạo bean PartnerClient, nhưng CI AOT bằng profile mặc định. Nếu bean graph khác nhau, executable có thể không chứa bean cần cho production.

Xử lý:

1. Xác định property/profile làm thay đổi condition.
2. Chọn build-time configuration có chủ đích.
3. Đưa cấu hình đó vào lệnh hoặc plugin configuration của AOT.
4. Kiểm tra generated context.
5. Chạy container với runtime configuration hợp lệ và xác minh bean cần thiết hoạt động.

Không đưa secret thật vào AOT processing. Dùng giá trị giả hoặc cấu hình không nhạy cảm cho các điều kiện cần đánh giá lúc build.

### 6.4. Chạy AOT-generated application trên JVM

Spring Boot cho phép khởi chạy JAR có chứa AOT-generated code trên JVM bằng system property `spring.aot.enabled=true`. Đây là một bước xác minh nhanh trước khi biên dịch native: nó kiểm tra generated initializer và ApplicationContext AOT mà không phải chờ native compilation.

Gradle, sau khi build JAR với Native Image plugin:

~~~bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/billing-service.jar
~~~

Maven, build package với profile native để chạy process-aot:

~~~bash
./mvnw -B -Pnative package
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

Trong terminal khác, gọi readiness và một API nghiệp vụ như khi test container. Dừng process bằng SIGTERM. JAR phải thực sự chứa AOT-generated classes/resources; nếu không, property trên không thể kiểm tra output AOT.

## 7. Cổng 3 — biên dịch Native Image

### 7.1. Biên dịch bằng Native Build Tools

Gradle:

~~~bash
./gradlew nativeCompile
~~~

Maven:

~~~bash
./mvnw -B -Pnative native:compile
~~~

Native Image compilation có thể tiêu tốn nhiều CPU và RAM. Runner cần được cấp đủ tài nguyên; nếu build bị kill, kiểm tra memory limit và compiler log trước khi thay đổi source.

### 7.2. Những lỗi cần xử lý tại cổng native

| Lỗi | Vùng kiểm tra |
| --- | --- |
| Missing reflection registration | RuntimeHints, dependency reachability metadata và dynamic call site |
| Missing proxy registration | JDK proxy interface list hoặc Spring AOT proxy generation |
| Serialization registration | Java serialization metadata hoặc binding hints của JSON/XML |
| Missing JNI registration | Native code truy cập class/member chưa được khai báo |
| Resource missing | Resource hints và resource patterns |
| Unsupported feature | Thư viện dùng dynamic class loading, thread hoặc API chưa hỗ trợ |
| Native library/linker failure | OS, architecture, libc, compiler và shared library |

Ưu tiên reachability metadata do framework hoặc dependency cung cấp. Chỉ thêm custom hints khi xác định được call site và loại truy cập động. Tracing Agent có thể giúp thu thập metadata, nhưng phải chạy qua những luồng nghiệp vụ cần thiết và review output.

### 7.3. Kiểm tra executable

Sau khi build, xác nhận:

~~~bash
file build/native/nativeCompile/billing-service
ldd build/native/nativeCompile/billing-service
~~~

Ví dụ trên giả định Linux binary liên kết động với glibc. Nếu dùng fully static musl, kiểm tra bằng ELF tools tương ứng; ldd có thể báo binary không liên kết động.

Với binary dynamic, kiểm tra:

- đúng architecture;
- dynamic loader tồn tại;
- không có dependency báo not found;
- glibc symbol version tương thích runtime image;
- CA certificates và resource ngoài executable được cung cấp.

Không chạy binary x86-64 trong image ARM64 hoặc binary glibc trong runtime musl chỉ vì Docker build thành công.

### 7.4. Chạy executable trực tiếp trước khi đóng gói

Khởi động binary trên runner hoặc môi trường Linux tương thích:

~~~bash
./build/native/nativeCompile/billing-service
~~~

Ở terminal khác, gọi readiness và một API nghiệp vụ. Dừng bằng SIGTERM và kiểm tra ứng dụng shutdown đúng cách.

Đây là smoke test nhanh cho executable. Nó vẫn chưa thay thế việc chạy trong container cuối, vì container có filesystem, user, network namespace và shared libraries riêng.

## 8. Cổng 4 — native tests

### 8.1. Gradle nativeTest

~~~bash
./gradlew nativeTest
~~~

Spring Boot Gradle plugin cấu hình AOT test tasks khi GraalVM Native Image plugin được áp dụng. Task nativeTest chạy các test sử dụng Spring TestContext Framework trong native mode theo phạm vi được hỗ trợ.

### 8.2. Maven nativeTest

~~~bash
./mvnw -B -PnativeTest test
~~~

Profile nativeTest do Spring Boot Starter Parent cung cấp sẽ xử lý test AOT và gọi Native Build Tools để chạy test native. Dự án không dùng Parent cần cấu hình các execution tương ứng.

### 8.3. Chọn test nào chạy native?

Ưu tiên test có rủi ro liên quan đến closed-world analysis:

- Spring ApplicationContext khởi tạo với profile quan trọng;
- controller serialize/deserialize request và response;
- HTTP client dùng DTO hoặc custom codec;
- reflection, proxy, serialization và resource lookup;
- security/transaction/async advice;
- database driver, JNI hoặc thư viện native;
- message listener và scheduled job quan trọng.

Không giả định mọi test JUnit đều tự động chạy native. Spring AOT test support tập trung vào test dùng Spring TestContext Framework; test framework hoặc extension không tương thích cần được xử lý riêng.

### 8.4. Lưu kết quả native test

Giữ report/log của nativeTest và ghi lại:

- test class nào được xử lý AOT;
- số test pass/fail/skip;
- GraalVM/JDK version;
- native test executable build options;
- thời gian compile và thời gian chạy.

Nếu nativeTest fail nhưng JVM test pass, giữ stack trace và xác định lỗi ở test AOT, native compilation hay runtime test. Không bỏ qua native test chỉ vì test JVM đã xanh.

## 9. Cổng 5 — đóng gói container từ executable đã kiểm tra

Pipeline có hai cách phổ biến để tạo image native. Chọn một cách cho một lần phát hành.

### 9.1. Cách A: đóng gói binary đã build bằng Dockerfile

Cách này phù hợp khi muốn kiểm soát rõ runtime image và bảo đảm binary trong image chính là artifact vừa chạy native tests.

Sau nativeCompile, copy executable vào build context:

Gradle:

~~~bash
mkdir -p docker/app
cp build/native/nativeCompile/billing-service docker/app/billing-service
chmod 0755 docker/app/billing-service
~~~

Maven, thay đường dẫn bằng output thực tế của Native Build Tools:

~~~bash
mkdir -p docker/app
cp target/billing-service docker/app/billing-service
chmod 0755 docker/app/billing-service
~~~

Ví dụ Dockerfile cho executable dynamic glibc build trên Ubuntu 24.04 runner:

~~~dockerfile
FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       libstdc++6 \
       zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY docker/app/billing-service /app/billing-service

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/billing-service"]
~~~

Ví dụ này dùng cùng baseline Ubuntu 24.04 cho runner và runtime. Danh sách package cần điều chỉnh theo output ldd của binary; không cài thêm thư viện theo phỏng đoán. Nếu build trên baseline khác, chọn runtime image tương thích với glibc symbol version và shared libraries mà executable yêu cầu. Với pipeline phát hành, pin base image bằng digest thay vì chỉ dùng tag để có thể tái lập image.

Nếu binary fully static musl và đã xác minh không cần shared library, có thể dùng runtime image scratch. Khi đó phải copy CA bundle, timezone hoặc resource ngoài binary mà ứng dụng cần. Static linking không tự nhúng các file hệ thống này.

### 9.2. Kiểm tra dependency trước khi build image

Với binary dynamic, chạy:

~~~bash
ldd docker/app/billing-service
~~~

Nếu kết quả có not found, bổ sung đúng runtime package hoặc sửa build environment. Không phát hành image chỉ vì Dockerfile build thành công; dynamic loader chỉ được gọi khi container khởi động.

Kiểm tra thêm:

~~~bash
file docker/app/billing-service
readelf -l docker/app/billing-service
readelf -d docker/app/billing-service
~~~

PT_INTERP cho biết dynamic loader; DT_NEEDED liệt kê shared libraries. Dùng các thông tin đó để chọn runtime image.

### 9.3. Build image

~~~bash
docker build --pull -f docker/Dockerfile.native \
  -t billing-service:ci .
~~~

Không nhúng secret vào Docker build arguments hoặc image layer. Runtime secret phải được cấp qua secret manager/orchestrator khi container chạy.

### 9.4. Cách B: dùng Cloud Native Buildpacks

Spring Boot hỗ trợ tạo native OCI image bằng Buildpacks.

Maven với Spring Boot Starter Parent và Native Build Tools plugin:

~~~bash
./mvnw -B -Pnative spring-boot:build-image
~~~

Gradle khi đã áp dụng GraalVM Native Image plugin:

~~~bash
./gradlew bootBuildImage
~~~

Spring Boot plugin tích hợp AOT và Native Image vào buildpack lifecycle. Buildpacks dùng builder/run image để tạo OCI image; không cần tự viết Dockerfile runtime cho trường hợp thông thường.

Với Spring Boot 4.2 và Buildpacks hiện hành, builder dùng GraalVM Native Image tương ứng với JDK dùng để biên dịch và yêu cầu tối thiểu JDK 25. Kiểm tra yêu cầu của Spring Boot/buildpack version đang pin; không suy ra JDK buildpack từ JDK runtime của container.

Trong nhánh Buildpacks, lệnh build-image/bootBuildImage thực hiện native compilation bên trong builder. Nếu đã chọn nhánh này, không cần chạy thêm nativeCompile chỉ để tạo một executable khác rồi bỏ đi. Vẫn giữ nativeTest làm cổng kiểm thử riêng trước khi tạo image.

Đặt builder/run image theo version hoặc digest được dự án kiểm tra. Với multi-module Maven, chỉ kích hoạt build-image ở module ứng dụng và cấu hình lifecycle của root POM theo cấu trúc dự án.

### 9.5. So sánh hai cách đóng gói

| Tiêu chí | Dockerfile với binary đã build | Buildpacks |
| --- | --- | --- |
| Nơi biên dịch native | Native Build Tools trên CI runner/build container | Bên trong builder |
| Runtime image | Nhóm phát triển chọn và quản lý | Buildpack chọn run image |
| Kiểm soát binary | Dễ xác minh binary hash giữa nativeCompile và image | Buildpack sở hữu lifecycle và layer |
| Toolchain | CI phải cài GraalVM/compiler phù hợp | Builder cung cấp toolchain theo buildpack |
| Tùy chỉnh OS package | Trực tiếp trong Dockerfile | Theo khả năng builder/buildpack |
| Cache | Build tool cache và Docker layer cache | Build/launch cache của CNB |

Chọn cách phù hợp với chuẩn container của tổ chức. Trong cả hai trường hợp, cổng cuối vẫn phải chạy đúng image vừa build.

## 10. Cổng 6 — kiểm chứng container cuối cùng

### 10.1. Kiểm tra metadata image

Sau khi build:

~~~bash
docker image inspect billing-service:ci
~~~

Xác nhận:

- image architecture đúng với target;
- entrypoint gọi native executable;
- user không phải root;
- port/container environment đúng;
- image có labels và digest để truy vết;
- không có secret hoặc file build/test không cần thiết.

Với Dockerfile ví dụ, kiểm tra user:

~~~bash
docker image inspect \
  --format '{{.Config.User}} {{.Config.Entrypoint}}' \
  billing-service:ci
~~~

Kết quả mong đợi có user 10001:10001 và entrypoint /app/billing-service.

### 10.2. Xác minh binary trong image là binary vừa build

Với cách Dockerfile, có thể trích executable từ image để so sánh:

~~~bash
docker create --name billing-image-check billing-service:ci
docker cp billing-image-check:/app/billing-service build/container-billing-service
docker rm billing-image-check
cmp docker/app/billing-service build/container-billing-service
~~~

Nếu cmp thành công, file trong image giống byte-for-byte với executable đã stage. Nếu dùng Buildpacks, đường dẫn executable phụ thuộc image layout; dùng cách kiểm tra tương ứng với builder hoặc kiểm tra provenance/SBOM của image.

### 10.3. Khởi chạy container

~~~bash
docker run -d \
  --name billing-service-check \
  -p 18080:8080 \
  billing-service:ci
~~~

Đợi readiness:

~~~bash
curl --fail http://127.0.0.1:18080/actuator/health/readiness
~~~

Sau đó gọi ít nhất một API nghiệp vụ:

~~~bash
curl --fail \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"customer-001","amount":125000}' \
  http://127.0.0.1:18080/api/invoices
~~~

Payload và endpoint là ví dụ. Thay bằng contract thực tế và xác nhận response body, status code, dữ liệu ghi xuống database hoặc kết quả gọi dependency.

### 10.4. Kiểm tra liveness, dependency và cấu hình runtime

Kiểm tra:

- readiness/liveness endpoint;
- database connection và reconnect;
- partner API DNS/TLS/certificate;
- runtime environment variables;
- mounted configuration và secret;
- log ra stdout/stderr;
- metrics endpoint nếu được bật;
- timezone/locale nếu nghiệp vụ phụ thuộc.

Không coi container start thành công là đủ. Container phải xử lý được các dependency và cấu hình mà production sẽ cung cấp.

### 10.5. Kiểm tra graceful shutdown

Gửi SIGTERM bằng Docker:

~~~bash
docker stop --time 30 billing-service-check
docker logs billing-service-check
~~~

Xác nhận Spring lifecycle dừng đúng, connection pool đóng và message listener ngừng nhận message theo policy. Nếu ứng dụng cần thời gian drain request, cấu hình shutdown timeout phù hợp với termination grace period của orchestrator.

## 11. GitHub Actions mẫu với Gradle và Dockerfile

Workflow sau minh họa Linux x86-64, GraalVM Community JDK 25, Gradle và runtime Ubuntu 24.04. Pin các version theo ma trận đã xác nhận của dự án; thay tên executable, endpoint và profile theo ứng dụng. Nếu dự án dùng Spring Boot/GraalVM release khác, chọn JDK được cặp version đó hỗ trợ.

~~~yaml
name: Spring Boot Native CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  native-container:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: graalvm-community
          java-version: '25'

      - uses: gradle/actions/setup-gradle@v6

      - name: Verify toolchain
        run: |
          java --version
          native-image --version
          docker version

      - name: JVM tests
        run: ./gradlew clean test

      - name: Spring AOT
        run: ./gradlew processAot

      - name: AOT mode JVM smoke
        run: |
          set -eu
          ./gradlew bootJar
          java -Dspring.aot.enabled=true -jar build/libs/billing-service.jar > build/aot-jvm.log 2>&1 &
          app_pid=$!
          cleanup() {
            kill -TERM "$app_pid" 2>/dev/null || true
            wait "$app_pid" || true
          }
          trap cleanup EXIT

          ready=false
          for attempt in $(seq 1 60); do
            if curl --fail --silent \
              http://127.0.0.1:8080/actuator/health/readiness >/dev/null; then
              ready=true
              break
            fi
            sleep 2
          done

          if [ "$ready" != true ]; then
            cat build/aot-jvm.log
            exit 1
          fi
          ./scripts/smoke-test.sh http://127.0.0.1:8080

      - name: Native compilation
        run: ./gradlew nativeCompile

      - name: Native tests
        run: ./gradlew nativeTest

      - name: Stage native executable
        run: |
          mkdir -p docker/app
          cp build/native/nativeCompile/billing-service docker/app/billing-service
          chmod 0755 docker/app/billing-service

      - name: Check native dependencies
        run: |
          set -eu
          file docker/app/billing-service
          ldd docker/app/billing-service | tee build/native-dependencies.txt
          if grep -q "not found" build/native-dependencies.txt; then
            echo "A native shared library is missing"
            exit 1
          fi

      - name: Build final container
        run: |
          docker build --pull \
            -f docker/Dockerfile.native \
            -t billing-service:$GITHUB_SHA .

      - name: Verify image user and entrypoint
        run: |
          docker image inspect \
            --format '{{.Config.User}} {{.Config.Entrypoint}}' \
            billing-service:$GITHUB_SHA
          test "$(docker image inspect --format '{{.Config.User}}' billing-service:$GITHUB_SHA)" = "10001:10001"

      - name: Verify binary copied into image
        run: |
          docker create --name billing-image-check billing-service:$GITHUB_SHA
          docker cp billing-image-check:/app/billing-service build/container-billing-service
          docker rm billing-image-check
          cmp docker/app/billing-service build/container-billing-service

      - name: Run final container smoke tests
        run: |
          set -eu
          name=billing-service-check
          image=billing-service:$GITHUB_SHA
          cleanup() {
            docker logs "$name" || true
            docker rm -f "$name" >/dev/null 2>&1 || true
          }
          trap cleanup EXIT

          docker run -d --name "$name" -p 18080:8080 "$image"

          ready=false
          for attempt in $(seq 1 60); do
            if curl --fail --silent \
              http://127.0.0.1:18080/actuator/health/readiness >/dev/null; then
              ready=true
              break
            fi
            sleep 2
          done

          if [ "$ready" != true ]; then
            echo "Container did not become ready"
            exit 1
          fi

          curl --fail http://127.0.0.1:18080/actuator/health/liveness
          ./scripts/smoke-test.sh http://127.0.0.1:18080

          docker stop --time 30 "$name"
~~~

Workflow dùng scripts/smoke-test.sh làm nơi gọi API nghiệp vụ của dự án. Script cần thất bại nếu response status/body hoặc side effect không đúng. Nếu chưa có script này, tạo test command phù hợp với contract API; không thay bằng một request health duy nhất.

### 11.1. Vì sao workflow kiểm tra binary hash?

Native tests chạy test executable riêng. NativeCompile tạo executable ứng dụng. Container build phải copy đúng executable từ nativeCompile. So sánh file trong image giúp phát hiện Dockerfile vô tình copy một binary cũ hoặc một file từ thư mục khác.

### 11.2. Biến thể Maven

Giữ nguyên các bước container verification, thay bước setup/build bằng lệnh Maven:

~~~bash
./mvnw -B clean verify
./mvnw -B -Pnative spring-boot:process-aot
./mvnw -B -Pnative native:compile
./mvnw -B -PnativeTest test
~~~

Stage executable từ target của module:

~~~bash
mkdir -p docker/app
cp target/billing-service docker/app/billing-service
chmod 0755 docker/app/billing-service
~~~

Đảm bảo native plugin đã đặt image name là billing-service hoặc điều chỉnh đường dẫn stage theo artifact thực tế.

## 12. Workflow thay thế: dùng Buildpacks tạo image native

Nếu tổ chức dùng Cloud Native Buildpacks, có thể rút gọn phần native compilation và container packaging:

Maven:

~~~bash
./mvnw -B clean verify
./mvnw -B -PnativeTest test
./mvnw -B -Pnative spring-boot:build-image \
  -Dspring-boot.build-image.imageName=billing-service:ci
~~~

Gradle:

~~~bash
./gradlew clean test
./gradlew nativeTest
./gradlew bootBuildImage
~~~

Đặt tên image Gradle rõ ràng để CI kiểm tra đúng artifact:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootBuildImage>("bootBuildImage") {
    imageName.set("billing-service:ci")
}
~~~

Với Gradle, cần áp dụng plugin org.graalvm.buildtools.native để Spring Boot plugin tạo native image. Với Maven, dùng Spring Boot Starter Parent và Native Build Tools plugin để profile native/nativeTest được cấu hình.

Buildpacks thực hiện AOT/native compilation trong lifecycle build image. Nếu muốn xem riêng AOT output trước đó, chạy processAot như một cổng kiểm tra bổ sung; tránh thêm nativeCompile vào cùng pipeline chỉ để tạo executable không được dùng.

Sau khi build image, chạy các bước container verification tương tự: inspect image, run readiness, API smoke, kiểm tra dependency, log và shutdown.

## 13. Maven và Gradle trong multi-module project

Với multi-module build, chỉ module chứa Spring Boot application cần tạo executable và OCI image. Các module library vẫn cần JVM tests và dependency outputs.

Maven:

- chạy verify ở root để test toàn bộ module;
- bật native profile ở module ứng dụng hoặc cấu hình profile root có chọn lọc;
- đảm bảo process-aot chạy sau khi dependency module đã package/compile;
- chỉ chạy spring-boot:build-image ở module ứng dụng.

Gradle:

- giữ plugin Spring Boot và Native Build Tools trong application module;
- module library cung cấp classpath và test outputs;
- gọi task nativeCompile/nativeTest theo path của application module;
- không áp dụng native plugin cho mọi library module nếu không tạo native executable ở đó.

Nếu dùng task path như :billing-service:nativeCompile, artifact nằm trong build directory của module tương ứng. Workflow phải stage đúng file từ module đó.

## 14. Phân vùng CI theo kiến trúc và môi trường

Native executable là artifact theo target platform. Nếu phát hành x86-64 và ARM64:

- chạy native build trên runner/VM có architecture tương ứng hoặc dùng cross-compilation được GraalVM hỗ trợ;
- tạo image cho từng architecture;
- tách build cache theo OS, architecture, libc và toolchain;
- chạy container test trên runtime architecture tương ứng;
- tạo manifest list sau khi từng image đã pass.

Không lấy executable x86-64 rồi gắn tag ARM64. Cũng không dùng image build trên glibc để chạy trong Alpine/musl nếu chưa build và kiểm thử đúng ABI.

Tách cấu hình:

| Môi trường | Cấu hình |
| --- | --- |
| Pull request | Test, AOT, native compile/test và container smoke; không có quyền publish production |
| Main branch | Chạy lại các gate, tạo image có provenance và lưu digest |
| Release tag | Dùng source commit đã duyệt, publish image theo version và digest |
| Deployment | Kéo đúng digest đã test; inject secret/runtime configuration từ hệ thống triển khai |

Không rebuild image sau khi test rồi publish image mới có tag tương tự. Digest là định danh nội dung bất biến của image.

## 15. Phân tích lỗi theo cổng

| Cổng thất bại | Bằng chứng cần thu thập | Hành động đầu tiên |
| --- | --- | --- |
| JVM tests | Test report, stack trace, dependency versions | Sửa regression/logic trước khi tiếp tục |
| AOT | Generated output, condition evaluation, AOT logs | Kiểm tra profile/property và bean definitions |
| Native compile | Native-image log, reachability report, toolchain | Phân loại reflection/proxy/resource/JNI hoặc linker |
| Native tests | Native test report, runtime exception | Tái hiện đúng Spring TestContext và call path |
| Docker build | Build log, Dockerfile, binary dependency list | Kiểm tra context, copy path và runtime packages |
| Container start | Container logs, exit code, image config | Kiểm tra loader, shared libraries, permission, port |
| Readiness | Health response và application logs | Kiểm tra startup, profile và dependency availability |
| API smoke | Request/response, downstream logs và database state | Kiểm tra contract, runtime config và network |
| Shutdown | Exit code, shutdown logs và timeout | Kiểm tra SIGTERM handling và lifecycle hooks |

Không sửa reachability metadata nếu lỗi thực tế là thiếu shared library hoặc sai architecture. Không thay runtime image khi lỗi là Spring bean bị loại bởi AOT condition. Phân loại đúng cổng giúp sửa đúng nguyên nhân.

## 16. Lưu artifact và bằng chứng của pipeline

Mỗi lần build native nên lưu:

- JVM test reports;
- AOT/native build logs;
- native test reports;
- executable checksum;
- GraalVM/JDK/Spring Boot/Native Build Tools versions;
- ldd/ELF dependency report nếu binary dynamic;
- Dockerfile hoặc builder/run image digest;
- OCI image digest và SBOM/provenance nếu pipeline hỗ trợ;
- kết quả readiness/API smoke;
- container logs và shutdown result.

Không lưu secret, token hoặc file cấu hình runtime nhạy cảm trong artifact. Dùng retention policy phù hợp với yêu cầu audit và dung lượng lưu trữ.

## 17. Checklist hoàn tất pipeline

- [ ] JVM unit/integration tests chạy trước native build.
- [ ] GraalVM/JDK, Spring Boot và Native Build Tools versions được pin.
- [ ] Spring AOT chạy với build-time profile/property đã xác định.
- [ ] Generated AOT output được kiểm tra khi cần chẩn đoán.
- [ ] Native executable được build thành công cho đúng OS/architecture.
- [ ] Native test chạy các Spring TestContext quan trọng.
- [ ] Reflection/proxy/serialization/resource/JNI hints đã được kiểm chứng qua luồng nghiệp vụ.
- [ ] Executable được kiểm tra bằng file/ELF tools và shared-library report.
- [ ] Runtime image tương thích libc và shared dependencies.
- [ ] CA certificates và runtime resources cần thiết có mặt.
- [ ] Container chạy bằng non-root user.
- [ ] Image entrypoint gọi native executable.
- [ ] Binary trong image trùng với binary đã stage hoặc có provenance tương ứng.
- [ ] Readiness và liveness pass trong container cuối.
- [ ] API smoke/integration test pass với dependency cần thiết.
- [ ] Graceful shutdown hoàn tất trong timeout.
- [ ] Image digest được lưu và dùng cho publish/deploy.
- [ ] Pull request không có quyền ghi cache hoặc publish artifact production.

**Ghi nhớ:** JVM tests xác nhận logic, AOT xác nhận ApplicationContext có thể được chuẩn bị ở build time, native compile xác nhận executable có thể tạo, native tests xác nhận các test context quan trọng chạy được trên native, còn container verification xác nhận đúng image phát hành có thể khởi động và xử lý nghiệp vụ trong runtime thực tế. Chỉ publish image digest sau khi tất cả cổng cần thiết đều pass.

## Tài liệu tham khảo

- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html): nativeTest với Maven/Gradle và phạm vi Spring TestContext.
- [Spring Boot — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): native executable và container image bằng Buildpacks.
- [Spring Boot Maven Plugin — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html): process-aot, process-test-aot và các profile native/nativeTest.
- [Spring Boot Gradle Plugin — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/gradle-plugin/aot.html): processAot, processTestAot và task nativeCompile/nativeTest.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html): imageName, native:compile, native:test và plugin configuration.
- [Spring Boot Maven Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html): build image bằng Cloud Native Buildpacks.
- [Spring Boot Gradle Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html): bootBuildImage và native image integration.
- [GraalVM — setup-graalvm GitHub Action](https://github.com/graalvm/setup-graalvm): chuẩn bị GraalVM JDK và native-image toolchain trong CI.
- [GitHub Actions — setup-java](https://github.com/actions/setup-java): cài JDK/GraalVM distribution và dependency cache trong workflow.
