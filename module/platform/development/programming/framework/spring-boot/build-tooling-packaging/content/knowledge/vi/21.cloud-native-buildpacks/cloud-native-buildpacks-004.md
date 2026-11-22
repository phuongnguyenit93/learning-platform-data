# Tạo image bằng Maven spring-boot:build-image

## 1. Tạo OCI image mà không cần tự viết Dockerfile

Khi một dự án Spring Boot cần chạy trong container, cách quen thuộc là tạo Dockerfile, chọn base image Java, copy JAR vào image rồi khai báo ENTRYPOINT. Cách đó vẫn phù hợp khi đội ngũ cần kiểm soát từng lệnh cài đặt hệ điều hành, thư mục, quyền file hoặc runtime packages.

Một lựa chọn khác là **Cloud Native Buildpacks (CNB)**. Spring Boot Maven Plugin tích hợp CNB qua goal:

~~~bash
./mvnw spring-boot:build-image
~~~

Goal này phân tích ứng dụng, chọn các buildpacks phù hợp, tạo runtime image và xuất một **OCI container image** vào Docker daemon. Với builder mặc định được tài liệu Spring Boot 3.5.16 mô tả, quy trình dùng hệ sinh thái Paketo. Bạn có thể build và chạy image mà không cần tự viết Dockerfile cho trường hợp ứng dụng Java thông thường.

Điểm quan trọng là **spring-boot:build-image không chỉ đổi tên JAR thành image**. Nó điều phối một quy trình có builder, buildpacks, build-time base image, run image, lifecycle, dependency layers và cache. Các thành phần đó quyết định JDK/JRE nào được cài, cách ứng dụng được đóng gói, process nào sẽ chạy và image cuối có những filesystem layers nào.

Bài học thuộc chủ đề cha **Cloud Native Buildpacks**. Chúng ta sẽ làm rõ CNB, builder và buildpack; cấu hình Maven goal; tạo một ứng dụng Java 17 có thể build; chạy image; cấu hình Java/buildpacks; hiểu Docker daemon, cache và registry; cuối cùng là chẩn đoán lỗi thường gặp và checklist cho CI.

## 2. Cloud Native Buildpacks là gì?

**Cloud Native Buildpacks** là một tiêu chuẩn và hệ sinh thái công cụ để biến mã nguồn hoặc application artifact thành OCI image theo những quy tắc có thể tái sử dụng. Thay vì tự viết các bước Dockerfile cho mọi ngôn ngữ, platform gọi những **buildpacks** chuyên biệt để nhận diện ứng dụng và đóng góp các thành phần cần thiết.

Một buildpack có thể:
- Nhận diện loại ứng dụng hoặc điều kiện đầu vào mà nó hỗ trợ.
- Cung cấp JDK/JRE, runtime, server hoặc thư viện cần thiết.
- Chuẩn bị artifact và môi trường khởi chạy.
- Tạo các dependency layers có thể cache và tái sử dụng.
- Ghi metadata, process type và Software Bill of Materials (SBOM) theo khả năng của buildpack.

Với Java, các buildpacks có thể nhận diện executable JAR, Maven/Gradle project hoặc ứng dụng Java khác, sau đó chọn cách đóng gói phù hợp. Spring Boot Maven Plugin giúp chuyển các cấu hình dự án Maven sang CNB platform mà không cần gọi riêng lệnh pack cho trường hợp phổ biến.

### 2.1. So sánh Dockerfile và Buildpacks

| Tiêu chí | Dockerfile | Cloud Native Buildpacks |
| --- | --- | --- |
| Đầu vào | Dockerfile + build context | Source hoặc application artifact + builder/buildpacks |
| Cách quyết định bước build | Người viết chỉ định lệnh | Buildpacks detect và thực hiện các build steps |
| Base image | FROM do người viết chọn | Builder cung cấp build image; builder metadata xác định run image |
| Java runtime | Người viết cài/copy JRE hoặc JDK | Java buildpack đóng góp JDK/JRE phù hợp |
| Tùy chỉnh | Rất trực tiếp qua Dockerfile | Qua builder, buildpacks, environment, bindings, project config |
| Image layers | Theo các Dockerfile instructions | Theo những dependency/application layers do buildpacks export |
| Phù hợp | Cần kiểm soát OS packages và quy trình đặc thù | Muốn quy trình chuẩn hóa, tự nhận diện ứng dụng và runtime |

Hai cách đều tạo OCI image và đều có thể được triển khai bằng Docker, Kubernetes hoặc nền tảng container tương thích. Buildpacks không loại bỏ nhu cầu hiểu image, registry, networking và runtime; chúng tự động hóa nhiều bước chuẩn bị image.

### 2.2. Khi nào nên dùng spring-boot:build-image?

Thường phù hợp khi:
- Ứng dụng là Spring Boot executable JAR/WAR theo layout plugin hỗ trợ.
- Muốn có runtime Java và non-root user theo cấu hình buildpack.
- Muốn dùng dependency caching và OCI layers mà không viết Dockerfile.
- Đội ngũ muốn chuẩn hóa build image qua nhiều Java services.
- Có thể dùng builder/buildpacks đã được kiểm soát và cập nhật theo policy.

Dockerfile hoặc custom builder có thể phù hợp hơn khi ứng dụng cần cài những OS packages đặc thù, cấu hình init/system tools riêng, ghép nhiều tiến trình không theo mô hình buildpack hoặc yêu cầu từng lệnh image phải được khai báo trực tiếp. Một số yêu cầu vẫn giải quyết được bằng custom buildpack hoặc builder extension.

## 3. Phân biệt buildpack, builder, build image và run image

Đây là bốn khái niệm dễ bị gọi chung là “buildpack image”, nhưng chúng có vai trò khác nhau.

### 3.1. Buildpack

**Buildpack** là một thành phần thực hiện công việc cụ thể. Ví dụ Java buildpack có thể nhận diện ứng dụng Java, cung cấp JDK/JRE, thiết lập classpath hoặc process và chuẩn bị các layer runtime.

Một builder có thể chứa nhiều buildpacks theo thứ tự. Mỗi buildpack sẽ được hỏi xem nó có hỗ trợ ứng dụng không trong giai đoạn detect. Các buildpacks được chọn sẽ chạy trong giai đoạn build.

### 3.2. Builder image

**Builder** là một OCI image dùng để thực hiện quá trình build. Theo CNB, builder chứa:
- Một danh sách có thứ tự các buildpacks và group.
- **Build-time base image**: môi trường để lifecycle/buildpacks chạy, có thể chứa build tools.
- CNB **lifecycle binaries** điều phối các giai đoạn.
- Metadata tham chiếu tới **run image** được dùng làm nền cho image cuối.

Builder là môi trường build, không phải mặc nhiên là image cuối chạy ứng dụng. Có thể có JDK, compilers và tooling trong build-time image, trong khi runtime image được chọn riêng.

### 3.3. Run image

**Run image** là base image của ứng dụng khi chạy. Nó cung cấp hệ điều hành và các thành phần runtime nền cần thiết. Builder metadata chỉ ra run image tương thích; Spring Boot Plugin dùng image đó mặc định nếu bạn không override.

Không chọn một run image bất kỳ chỉ vì nó có Java. Run image phải tương thích với builder/stack mà buildpacks đã dùng. Khi thay builder hoặc run image, cần kiểm tra compatibility và policy cập nhật của cả cặp.

### 3.4. Image cuối

Sau khi buildpacks đóng góp ứng dụng, JRE và các lớp cần thiết, lifecycle export thành một **OCI image**. Image đó là đầu ra bạn chạy bằng Docker hoặc đẩy lên registry.

~~~text
Maven project
     |
     v
spring-boot:build-image
     |
     v
CNB platform + Builder
     |
     +--> Build-time base image
     +--> Lifecycle
     +--> Ordered buildpacks
     +--> Run image reference
                |
                v
        Analyze / Detect / Restore
                |
                v
               Build
                |
                v
              Export
                |
                v
          OCI application image
~~~

**Builder image** dùng để tạo image. **Run image** làm nền cho image cuối. **Application image** mới là image mà container chạy.

## 4. CNB lifecycle diễn ra như thế nào?

Spring Boot Maven Plugin điều phối CNB lifecycle thông qua Docker daemon. Ở mức khái niệm, các giai đoạn chính:

| Giai đoạn | Việc thực hiện | Kết quả |
| --- | --- | --- |
| **Analyze** | Đọc metadata image trước đó và thông tin cache | Xác định các layer đã có thể tái sử dụng |
| **Detect** | Hỏi các buildpacks xem chúng có nhận diện ứng dụng không và chọn group phù hợp | Build plan |
| **Restore** | Khôi phục các dependency/application layers từ cache trước | Các lớp cache sẵn sàng |
| **Build** | Chạy những buildpacks đã được chọn | Dependencies, app output, metadata và layers |
| **Export** | Ghép các lớp và metadata để xuất image | OCI image và cache mới |

CNB lifecycle còn có những thành phần/chi tiết khác theo Platform API và phiên bản lifecycle. Bảng trên giúp hiểu luồng của một lần build thông thường.

### 4.1. Analyze và cache

Khi đã có image trước đó, lifecycle có thể đọc metadata và kiểm tra các layer để xác định phần nào không đổi. Spring Boot Plugin lưu cache trong Docker named volumes theo mặc định; cache giúp giảm công việc build lại những dependencies hoặc nội dung có thể tái sử dụng.

### 4.2. Detect

Buildpacks kiểm tra ứng dụng. Với một Spring Boot Maven project, Java buildpack có thể nhận diện cấu trúc dự án và executable archive. Nếu không có buildpack nào nhận diện được ứng dụng, quá trình detect thất bại và không có image hợp lệ để export.

Một lỗi detect có thể là dấu hiệu:
- Chọn sai builder.
- Builder không chứa buildpack phù hợp.
- Application artifact chưa được tạo hoặc không nằm trong source directory mà plugin đang dùng.
- Dự án có layout/packaging không được buildpack hiện tại hỗ trợ.

### 4.3. Build và Export

Buildpacks cung cấp runtime components, xử lý application artifact và tạo các layers. Export tạo image dựa trên run image, ghi metadata/process và xuất cache. Build output có thể chứa nhiều filesystem layers thay vì một layer duy nhất chứa toàn bộ ứng dụng.

**Buildpacks không tự động đảm bảo image nhỏ nhất hoặc startup nhanh nhất cho mọi ứng dụng.** Kết quả phụ thuộc builder, buildpack versions, JRE provider, dependencies, application layout và runtime configuration.

## 5. spring-boot:build-image thực hiện điều gì?

Goal **spring-boot:build-image** của Spring Boot Maven Plugin 3.5.16:
- Fork Maven lifecycle để bảo đảm phase **package** đã chạy.
- Tạo executable archive cần thiết nếu chưa có.
- Đưa ứng dụng vào CNB builder.
- Chạy buildpacks để tạo OCI image.
- Mặc định tạo image cục bộ trong Docker daemon.
- Có thể publish image lên registry khi bật tùy chọn publish.

**Không bắt buộc chạy riêng spring-boot:repackage trước** để build-image có executable archive; goal có thể tạo archive cần thiết và áp dụng các thiết lập packaging tương ứng.

### 5.1. Lệnh đơn giản nhất

Tại thư mục gốc dự án có Maven Wrapper:

~~~bash
./mvnw spring-boot:build-image
~~~

Nếu dùng Maven cài trên máy:

~~~bash
mvn spring-boot:build-image
~~~

Trên Windows:

~~~powershell
.mvnw.cmd spring-boot:build-image
~~~

Goal sẽ chạy package lifecycle rồi build image. Nếu build thành công, image thường có tên mặc định theo **artifactId** và **version** của Maven project:

~~~text
docker.io/library/<artifactId>:<version>
~~~

Ví dụ project có artifactId là **cnb-demo** và version **1.0.0**, tên mặc định:

~~~text
docker.io/library/cnb-demo:1.0.0
~~~

Bạn có thể kiểm tra image bằng:

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0
~~~

Image được tạo ở Docker daemon mà plugin đang kết nối; nó không mặc định được push lên registry.

### 5.2. Khác biệt giữa build-image và build-image-no-fork

Hai goal có mục đích gần nhau nhưng cách tham gia Maven lifecycle khác nhau:

| Goal | Cách gọi | Ý nghĩa |
| --- | --- | --- |
| **build-image** | Gọi trực tiếp từ command line | Fork lifecycle để bảo đảm package đã chạy |
| **build-image-no-fork** | Dùng trong plugin execution được gắn vào lifecycle | Không fork lifecycle lần nữa |

Dùng **build-image** cho lệnh trực tiếp:

~~~bash
./mvnw spring-boot:build-image
~~~

Nếu muốn image tự build khi chạy Maven package, có thể bind **build-image-no-fork**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>build-image-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Không bind **build-image** vào chính phase package theo kiểu fork lặp lại. Goal **build-image-no-fork** được thiết kế cho trường hợp lifecycle execution; gọi trực tiếp trên command line thì dùng **build-image**.

## 6. Điều kiện cần: Docker daemon

Goal cần truy cập một Docker daemon để:
- Pull builder và run images.
- Tạo builder container và volumes.
- Truy cập cache.
- Export image vào image store hoặc publish lên registry.

Trước khi build, kiểm tra:

~~~bash
docker version
docker info
docker context ls
docker context show
~~~

Nếu Docker CLI cũng không kết nối được daemon, cần sửa Docker Engine/Desktop/Podman context trước. Nếu Docker CLI hoạt động nhưng Maven plugin không kết nối được, kiểm tra context và các biến môi trường mà Maven process nhận.

### 6.1. Docker context và biến môi trường

Spring Boot Plugin đọc Docker CLI configuration để xác định context hiện tại. Các biến thường dùng:

| Biến | Tác dụng |
| --- | --- |
| **DOCKER_CONFIG** | Thư mục cấu hình Docker CLI; mặc định thường là thư mục .docker trong home |
| **DOCKER_CONTEXT** | Tên Docker context cần dùng; ưu tiên hơn DOCKER_HOST |
| **DOCKER_HOST** | URL của Docker daemon, ví dụ tcp://host:2376 |
| **DOCKER_TLS_VERIFY** | Bật TLS verification khi giá trị là 1 |
| **DOCKER_CERT_PATH** | Đường dẫn certificates khi dùng TLS |

Ví dụ khi cần dùng một Docker context có sẵn:

~~~bash
docker context use desktop-linux
./mvnw spring-boot:build-image
~~~

Tên context phụ thuộc máy; kiểm tra bằng **docker context ls**, không mặc định mọi máy đều có desktop-linux.

Nếu dùng daemon từ xa qua TLS, cấu hình đúng host và certificate theo policy. Không mở Docker TCP socket không xác thực ra mạng công cộng; quyền điều khiển Docker daemon thường tương đương quyền cao trên host.

### 6.2. Cấu hình Docker host trong POM

Plugin cũng hỗ trợ tham số Docker:

~~~xml
<docker>
    <host>tcp://docker-builder.internal:2376</host>
    <tlsVerify>true</tlsVerify>
    <certPath>/secure/docker-certs</certPath>
</docker>
~~~

Đây là **đoạn cấu hình minh họa**, không phải host hoặc certificate có sẵn. Thư mục cert phải tồn tại trên máy chạy Maven và được bảo vệ theo policy. Nếu Docker context đã được cấu hình đúng, không cần khai báo lại host trong POM.

### 6.3. Docker Desktop, Podman, Colima

Spring Boot 3.5.16 có hướng dẫn kết nối với các môi trường như Docker Engine, minikube, Podman và Colima. Với những môi trường này, điều quan trọng là plugin phải nhận đúng endpoint/socket của daemon.

Ví dụ trên Linux/macOS khi dùng Docker context Colima, có thể lấy endpoint theo tài liệu CLI của Colima rồi gán vào DOCKER_HOST. Đường dẫn socket cụ thể phụ thuộc user và cấu hình máy; không copy cứng một socket path của máy khác.

Với Podman, plugin có thể được cấu hình qua host socket và bindHostToBuilder. Hãy xác nhận daemon socket đã được bật và builder container có thể truy cập các dịch vụ mạng cần thiết.

## 7. Ví dụ thực hành: Spring Boot Java 17

Chúng ta tạo một ứng dụng web nhỏ để build image và kiểm tra sau khi chạy. Ví dụ sử dụng **Java 17** và **Spring Boot 3.5.16**; đây là tổ hợp minh họa, không phải khuyến nghị bất biến cho mọi dự án mới.

### 7.1. Cấu trúc dự án

~~~text
cnb-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/cnb/
    │   │   ├── CnbDemoApplication.java
    │   │   └── HelloController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/cnb/
            └── HelloControllerTest.java
~~~

Maven Wrapper phải được tạo bằng Spring Initializr hoặc Maven Wrapper plugin. Tệp **mvnw**, **mvnw.cmd** và **.mvn/wrapper** phải được commit cùng dự án để các máy dùng cùng Maven distribution.

### 7.2. Main class

Tệp **src/main/java/com/example/cnb/CnbDemoApplication.java**:

~~~java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CnbDemoApplication.class, args);
    }
}
~~~

### 7.3. Controller

Tệp **src/main/java/com/example/cnb/HelloController.java**:

~~~java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello-from-buildpacks";
    }
}
~~~

Khi ứng dụng đã khởi động và request GET /hello thành công, response body chính xác:

~~~text
hello-from-buildpacks
~~~

### 7.4. application.properties

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=cnb-demo
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
~~~

Cấu hình này đặt HTTP port là 8080 và bật các health probe groups của Spring Boot. Ứng dụng có thể được kiểm tra qua **/actuator/health/readiness** sau khi thêm Actuator dependency.

### 7.5. Test controller

Tệp **src/test/java/com/example/cnb/HelloControllerTest.java**:

~~~java
package com.example.cnb;

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
class HelloControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void helloReturnsExpectedText() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("hello-from-buildpacks"));
    }
}
~~~

Test xác minh Spring context và controller trong Maven test environment. Sau đó vẫn cần chạy image thật để kiểm tra runtime JRE, process, port và container networking.

## 8. POM đầy đủ để tạo image bằng Buildpacks

Tệp **pom.xml**:

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
    <artifactId>cnb-demo</artifactId>
    <version>1.0.0</version>

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
                        <name>docker.io/library/cnb-demo:${project.version}</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                    <createdDate>2026-01-01T00:00:00Z</createdDate>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:
- **spring-boot-starter-parent** quản lý dependency/plugin versions và tích hợp các executions phù hợp.
- **java.version=17** đặt Java compatibility cho compilation.
- **spring-boot-starter-web** cung cấp Spring MVC và embedded server.
- **spring-boot-starter-actuator** cung cấp health endpoints.
- **spring-boot-starter-test** chỉ dùng cho tests.
- **spring-boot-maven-plugin** cung cấp goal build-image.
- **image.name** đặt image reference rõ ràng theo artifact version.
- **BP_JVM_VERSION=17** yêu cầu Paketo Java buildpack dùng Java major version 17.
- **createdDate** là metadata timestamp cố định cho ví dụ reproducible build; chọn giá trị phù hợp với release policy thực tế.

Trong POM này không cần viết Dockerfile. Builder mặc định của Spring Boot 3.5.16 là **paketobuildpacks/builder-noble-java-tiny:latest**; builder metadata cung cấp run image tương thích. Với môi trường release, nên chọn builder tag/digest đã được phê duyệt và quản lý cập nhật, thay vì dựa mãi vào tag mutable latest.

**Lưu ý về createdDate:** giá trị cố định giúp metadata image tái lập tốt hơn, nhưng chưa đủ bảo đảm toàn bộ image giống nhau từng byte. Cần kiểm soát builder/buildpack versions, run image, dependencies, platform và mọi nguồn build metadata khác.

## 9. Build và chạy image lần đầu

Từ thư mục project root:

~~~bash
./mvnw -B -ntp clean verify
./mvnw spring-boot:build-image
~~~

Lệnh thứ hai sẽ chạy package lifecycle theo cơ chế goal. Có thể gọi trực tiếp chỉ một lệnh:

~~~bash
./mvnw spring-boot:build-image
~~~

Khi build hoàn tất, kiểm tra image local:

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0
~~~

Chạy container:

~~~bash
docker run --rm --name cnb-demo   -p 127.0.0.1:18080:8080   cnb-demo:1.0.0
~~~

Từ terminal khác:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/hello
~~~

Body mong đợi:

~~~text
hello-from-buildpacks
~~~

Kiểm tra readiness:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health/readiness
~~~

Sau khi ứng dụng sẵn sàng và không có health indicator lỗi, response thường là:

~~~json
{"status":"UP"}
~~~

**docker run** và HTTP response là hai bước khác nhau. Nếu container không start hoặc endpoint không trả về, xem logs, port mapping và cấu hình runtime trước khi kết luận buildpacks tạo image sai.

### 9.1. Chạy container detached để xem logs

~~~bash
docker run -d --name cnb-demo-test   -p 127.0.0.1:18080:8080   cnb-demo:1.0.0

docker ps -a --filter "name=cnb-demo-test"
docker logs --tail 80 cnb-demo-test
~~~

Sau khi kiểm thử:

~~~bash
docker stop --time 15 cnb-demo-test
docker rm cnb-demo-test
~~~

Chỉ xóa container thử nghiệm mà bạn đã tạo. Không chạy lệnh xóa hàng loạt container/image/cache trên Docker daemon dùng chung.

## 10. Tùy chỉnh builder và run image

Spring Boot 3.5.16 mặc định sử dụng builder:

~~~text
paketobuildpacks/builder-noble-java-tiny:latest
~~~

Bạn có thể chọn builder khác qua POM:

~~~xml
<image>
    <builder>paketobuildpacks/builder-noble-java-tiny:latest</builder>
</image>
~~~

Hoặc command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.builder=paketobuildpacks/builder-noble-java-tiny:latest
~~~

Tag **latest** có thể thay đổi theo lần publish. Trong CI/release, nên pin version tag cụ thể hoặc digest được duyệt, đồng thời kiểm soát run image tương ứng.

### 10.1. Run image

Builder metadata chỉ định run image mặc định. Nếu cần thay run image, cấu hình:

~~~xml
<image>
    <builder>registry.example.com/platform/java-builder:1.2.0</builder>
    <runImage>registry.example.com/platform/java-run:1.2.0</runImage>
</image>
~~~

Tên registry và versions ở đây là ví dụ. Run image phải tương thích với builder stack/API và những thành phần buildpacks đã tạo. Không thay bằng một base image tùy ý rồi kỳ vọng application layers vẫn chạy.

Có thể override qua command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.builder=registry.example.com/platform/java-builder:1.2.0   -Dspring-boot.build-image.runImage=registry.example.com/platform/java-run:1.2.0
~~~

### 10.2. Builder có phải runtime image không?

Không. Builder image chứa môi trường để thực hiện buildpacks và lifecycle. Run image là base cho ứng dụng khi chạy. Image cuối được export từ run image cộng với những layers mà buildpacks đã đóng góp.

Nếu builder quá cũ, buildpack có thể không hiểu source/artifact hiện tại. Nếu run image không tương thích, image có thể build nhưng lỗi lúc runtime do thiếu thư viện hệ điều hành hoặc ABI không khớp. Cần cập nhật builder/run image theo cặp và chạy smoke test sau khi thay đổi.

## 11. Chọn platform và pull policy

### 11.1. imagePlatform

Spring Boot Maven Plugin từ 3.4 hỗ trợ cấu hình platform cho builder, run và buildpack images:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imagePlatform=linux/amd64
~~~

Một số giá trị ví dụ:

~~~text
linux/amd64
linux/arm64
linux/arm/v7
~~~

Platform phải được builder hỗ trợ. Chọn platform phù hợp với nơi image sẽ chạy. Nếu build trên ARM laptop nhưng production là AMD64, cấu hình platform rõ ràng để tránh tạo image khác kiến trúc.

### 11.2. pullPolicy

Spring Boot Plugin hỗ trợ ba lựa chọn:

| Giá trị | Hành vi |
| --- | --- |
| **ALWAYS** | Luôn kiểm tra/pull builder và run images từ registry |
| **IF_NOT_PRESENT** | Chỉ pull khi image chưa có local |
| **NEVER** | Không pull; yêu cầu các images cần thiết đã có local |

Mặc định được tài liệu Spring Boot 3.5.16 ghi là **ALWAYS**. Điều này giúp lấy image mới nhất theo tag nhưng có thể làm build chậm hơn hoặc không tái lập nếu tag mutable.

Ví dụ dùng cache local khi đã chuẩn bị sẵn builder/run images:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.pullPolicy=IF_NOT_PRESENT
~~~

**NEVER** chỉ nên dùng khi bạn chắc chắn tất cả builder/run/buildpack images cần thiết đã có trên daemon và không cần pull. Nếu thiếu image, build sẽ fail.

## 12. Đặt image name và tags

Tên image mặc định được suy ra từ Maven **artifactId** và **version**, ví dụ:

~~~text
docker.io/library/cnb-demo:1.0.0
~~~

Có thể đặt tên trong POM:

~~~xml
<image>
    <name>registry.example.com/team/cnb-demo:${project.version}</name>
</image>
~~~

Hoặc command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-demo:1.0.0
~~~

Image reference có dạng:

~~~text
[registry-host[:port]/][namespace/]image-name[:tag]
~~~

Nếu không chỉ định registry, Docker Hub thường được hiểu là registry mặc định. Nếu không chỉ định path, namespace mặc định thường là library; nếu không chỉ định tag, tag mặc định là latest.

### 12.1. Additional tags

Plugin hỗ trợ thêm một hoặc nhiều full image references làm tags. Khi cấu hình nhiều tags, cần cung cấp đầy đủ registry/path/name/tag theo định dạng tài liệu. Tránh dùng tag latest làm định danh duy nhất của một release; hãy giữ tag version/commit rõ ràng để trace.

Tag chỉ là tên tham chiếu. Cùng một image có thể được gắn nhiều tags; thay tag không tự thay bytes của image.

### 12.2. Xác nhận image local

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0 --format '{{.Id}}'
docker image inspect cnb-demo:1.0.0 --format '{{.Os}}/{{.Architecture}}'
docker image inspect cnb-demo:1.0.0 --format '{{.Config.User}}'
docker image history cnb-demo:1.0.0
~~~

Spring Boot documentation nêu image được build và chạy bằng **non-root user** vì lý do bảo mật. Kiểm tra cấu hình image thật để xác nhận user và process; đừng giả định mọi builder tùy chỉnh đều giữ nguyên chính sách này.

## 13. Publish image lên registry

Mặc định:

~~~text
publish = false
~~~

Goal tạo image local nhưng không tự push. Để publish, có thể dùng command line:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-demo:1.0.0   -Dspring-boot.build-image.publish=true
~~~

Khi publish bật, registry đích được xác định bởi phần registry trong image name. Cần xác nhận tag/repository đúng trước khi bật publish trong pipeline.

### 13.1. Đăng nhập registry

Nếu registry dùng Docker CLI credential helper hoặc credential store, plugin có thể đọc cấu hình Docker hiện có (thường ở thư mục .docker). Ví dụ:

~~~bash
docker login registry.example.com
./mvnw spring-boot:build-image   -Dspring-boot.build-image.imageName=registry.example.com/team/cnb-demo:1.0.0   -Dspring-boot.build-image.publish=true
~~~

Không đưa mật khẩu thật vào shell history hoặc commit POM. Trong CI, dùng credential store/secret injection theo policy của runner.

### 13.2. Hai loại registry credentials

Cần phân biệt:
- **builderRegistry**: xác thực khi pull builder image hoặc run image từ registry riêng.
- **publishRegistry**: xác thực khi push image ứng dụng do buildpacks tạo ra.

Chúng phục vụ hai luồng khác nhau. Nếu builder/run image ở registry riêng, cấu hình builderRegistry; nếu image ứng dụng publish lên registry riêng, cấu hình publishRegistry. Một Docker login phù hợp cũng có thể cung cấp credentials qua Docker config.

Ví dụ cấu trúc cấu hình, dùng biến môi trường của CI thay credentials thật:

~~~xml
<docker>
    <builderRegistry>
        <username>${env.BUILDER_REGISTRY_USER}</username>
        <password>${env.BUILDER_REGISTRY_PASSWORD}</password>
        <url>https://registry.example.com</url>
    </builderRegistry>
    <publishRegistry>
        <username>${env.APP_REGISTRY_USER}</username>
        <password>${env.APP_REGISTRY_PASSWORD}</password>
        <url>https://registry.example.com</url>
    </publishRegistry>
</docker>
~~~

Đây là cấu hình minh họa. Kiểm tra tên property/environment variables và authentication scheme của registry tổ chức đang dùng. Không in credentials vào Maven logs; hạn chế quyền token theo repository và thời hạn.

### 13.3. Xác nhận sau publish

Sau khi push thành công, dùng registry tooling hoặc Docker pull trên một máy/runner có quyền:

~~~bash
docker pull registry.example.com/team/cnb-demo:1.0.0
docker image inspect registry.example.com/team/cnb-demo:1.0.0
~~~

Build success và push success là hai kết quả khác nhau. Trong release evidence nên ghi image digest, source commit, builder/buildpack versions và registry reference. Tag có thể bị ghi đè; digest là định danh nội dung phù hợp hơn cho triển khai đã chốt.

## 14. Cấu hình Java buildpack

Với Paketo Java buildpack, biến build-time quan trọng:

~~~text
BP_JVM_VERSION
~~~

Ví dụ trong POM:

~~~xml
<image>
    <env>
        <BP_JVM_VERSION>17</BP_JVM_VERSION>
    </env>
</image>
~~~

Hoặc command line khi cấu hình environment qua POM/property phù hợp. Trong trường hợp Spring Boot Plugin dùng default Paketo builder, plugin có thể đọc Java compatibility của Maven compiler và hướng dẫn buildpack cài cùng Java version. Ghi BP_JVM_VERSION tường minh giúp thể hiện ý định và tránh phụ thuộc cấu hình compiler không rõ ràng.

### 14.1. JDK và JRE

Paketo Java buildpack mặc định thường dùng JDK cho build-time và JRE cho runtime khi có dependency phù hợp. Biến:

~~~text
BP_JVM_TYPE
~~~

có thể điều khiển loại JVM mà buildpack cài. Cân nhắc kỹ trước khi yêu cầu JDK trong runtime image: JDK lớn hơn và chứa nhiều công cụ hơn mức ứng dụng cần.

Một số buildpack/provider hỗ trợ tạo JRE tối giản qua JLink. Biến:

~~~text
BP_JVM_JLINK_ENABLED=true
~~~

có thể bật cơ chế đó khi provider/version phù hợp. Không bật chỉ để giảm size mà chưa kiểm tra các Java modules mà ứng dụng hoặc thư viện cần.

### 14.2. Runtime JVM options

Ở runtime, Paketo Java buildpack cung cấp các biến cấu hình như:
- **BPL_JVM_HEAD_ROOM**
- **BPL_JVM_LOADED_CLASS_COUNT**
- **BPL_JVM_THREAD_COUNT**
- **BPL_JVM_CLASS_ADJUSTMENT**
- **JAVA_TOOL_OPTIONS**

Các biến BPL điều chỉnh runtime components mà buildpack cung cấp, ví dụ JVM memory calculator. JAVA_TOOL_OPTIONS là cơ chế Java tiêu chuẩn để truyền JVM flags.

Ví dụ chạy container:

~~~bash
docker run --rm   -e JAVA_TOOL_OPTIONS="-Dserver.port=8081"   -p 8081:8081   cnb-demo:1.0.0
~~~

Ví dụ này thay server port qua system property. Nếu ứng dụng có cấu hình server.port khác hoặc security requirements, phải kiểm tra lại endpoint và mapping.

### 14.3. Build-time và runtime environment không giống nhau

| Nhóm | Prefix/biến | Thời điểm áp dụng |
| --- | --- | --- |
| Buildpack configuration | **BP_** | Khi tạo image |
| Buildpack runtime component | **BPL_** | Khi container chạy |
| Java standard options | **JAVA_TOOL_OPTIONS** | JVM runtime |
| Embedded environment modifications | **BPE_** | Được build vào image nếu có Environment Variables buildpack |

**Không nhầm BP_JVM_VERSION với biến môi trường container runtime**. Thay BP_JVM_VERSION cần rebuild image. Thay JAVA_TOOL_OPTIONS lúc docker run có thể đổi JVM behavior mà không build lại image.

### 14.4. Không nhúng secret vào image

Paketo Environment Variables buildpack có thể embed các biến mặc định vào image thông qua BPE_*. Những giá trị đó trở thành metadata/content mà người có quyền đọc image có thể xem.

**Không embed password, API token, private key hoặc database credentials vào image**. Dùng secret manager, orchestrator secret hoặc buildpack bindings cho những credentials cần thiết ở build/runtime. Giá trị cấu hình không nhạy cảm như một JVM flag mặc định có thể phù hợp với embedded environment khi policy cho phép.

## 15. Proxy và network trong buildpacks

Trong quá trình build, builder container và buildpacks có thể cần tải JDK, dependency hoặc metadata từ registry/remote sources. Việc máy host truy cập internet được không bảo đảm builder container cũng có cùng network/proxy.

Với Paketo, có thể truyền proxy environment qua cấu hình image:

~~~xml
<image>
    <env>
        <HTTP_PROXY>http://proxy.example.com:8080</HTTP_PROXY>
        <HTTPS_PROXY>http://proxy.example.com:8080</HTTPS_PROXY>
    </env>
</image>
~~~

Đây là proxy giả định; dùng endpoint đã được tổ chức phê duyệt. Tránh ghi credentials proxy vào POM hoặc Maven logs.

Plugin còn có tham số **network** để cấu hình network driver của builder container. Giá trị được chuyển cho Docker; cần bảo đảm network tồn tại và builder container có quyền truy cập các dịch vụ cần thiết.

Nếu build lỗi khi tải JDK hoặc dependencies, xem:
1. Docker daemon có pull được builder/run images không?
2. Builder container có DNS và network không?
3. Proxy variables có được truyền đúng vào builder không?
4. Registry/artifact mirror có yêu cầu credentials không?
5. CA certificate của proxy/private registry đã được tin cậy chưa?

## 16. Builder cache và workspace

Spring Boot Plugin dùng các cache volumes để lưu layers được tạo trong build/launch. Mặc định, cache volumes có tên suy ra từ **full image name**.

Điều này có một hệ quả thực tế: nếu image name chứa version thay đổi liên tục, ví dụ:

~~~text
cnb-demo:1.0.0
cnb-demo:1.0.1
cnb-demo:1.0.2
~~~

thì cache volumes mặc định có thể khác nhau theo image name, làm giảm khả năng tái sử dụng cache giữa các bản phát hành.

### 16.1. cleanCache

Tham số **cleanCache** mặc định là false. Khi đặt true, plugin xóa cache trước build:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.cleanCache=true
~~~

Dùng khi điều tra cache corruption hoặc cần xác minh build cold. Không bật mỗi lần build trong CI thông thường nếu muốn tận dụng cache; thao tác này có thể làm build chậm và tăng tải mạng.

### 16.2. Tùy chỉnh cache volume

Có thể đặt tên cache volumes rõ ràng trong POM:

~~~xml
<image>
    <buildCache>
        <volume>
            <name>cnb-demo-build-cache</name>
        </volume>
    </buildCache>
    <launchCache>
        <volume>
            <name>cnb-demo-launch-cache</name>
        </volume>
    </launchCache>
</image>
~~~

Cache build và cache launch phục vụ các layer khác nhau. Chọn tên ổn định theo project/branch policy; tránh cho các project không liên quan dùng chung volume nếu không có thiết kế kiểm soát. Nếu nhiều CI jobs chạy song song, cần xem xét cách builder và Docker daemon quản lý cache volume để tránh tranh chấp.

### 16.3. Workspace

**buildWorkspace** là vùng tạm cho builder/buildpacks xử lý files trong quá trình build. Mặc định plugin dùng named volume trên Docker daemon. Có thể đổi sang bind mount nếu môi trường cần quản lý đường dẫn hoặc storage cụ thể.

Không xóa thủ công named volumes đang được build khác dùng. Khi cần dọn cache, xác định chính xác volume do project tạo và thực hiện theo policy của runner.

## 17. Reproducible image và createdDate

Spring Boot Maven Plugin có tham số **createdDate** cho trường Created trong metadata image. Giá trị có thể là:
- ISO 8601 instant, ví dụ 2026-01-01T00:00:00Z.
- **now**, nghĩa là thời điểm hiện tại.

Một mốc cố định giúp image metadata tái lập hơn:

~~~bash
./mvnw spring-boot:build-image   -Dspring-boot.build-image.createdDate=2026-01-01T00:00:00Z
~~~

Trong POM có thể cấu hình:

~~~xml
<createdDate>2026-01-01T00:00:00Z</createdDate>
~~~

Nếu dùng **now**, cùng source build ở các thời điểm khác nhau sẽ có metadata Created khác nhau. Với release cần reproducibility, lấy timestamp từ release/commit metadata đã chốt và dùng nhất quán.

**createdDate không đủ để bảo đảm image giống nhau từng byte.** Còn phải kiểm soát:
- Builder/run image versions và digests.
- Buildpack versions.
- JDK/JRE provider và patch versions.
- Dependencies, repositories và artifact inputs.
- Platform/architecture.
- Generated metadata, timestamps và build environment.
- Cấu hình cache và lifecycle.

Một image reproducible còn cần xác minh bằng cách build lại và so digest/artifact trong môi trường được kiểm soát. Không suy luận reproducibility chỉ từ một dòng createdDate.

## 18. Buildpacks tạo OCI image như thế nào về mặt output?

CNB export tạo image gồm những filesystem layers và metadata cần thiết. Image thường có:
- Runtime base từ run image.
- Các dependency/runtime layers do buildpacks đóng góp.
- Application layer.
- Metadata mô tả process, buildpacks, stack/run image và các thông tin build.
- SBOM hoặc BOM metadata tùy buildpack/platform và phiên bản.

Không nên dự đoán một số layer cố định cho mọi ứng dụng. Một Java buildpack có thể đóng góp JRE, classpath, application và những component runtime khác; mỗi buildpack version hoặc cấu hình có thể thay đổi số lớp.

### 18.1. Kiểm tra image history

~~~bash
docker image history cnb-demo:1.0.0
docker image inspect cnb-demo:1.0.0
~~~

CNB images không nhất thiết có history giống Dockerfile thủ công. Những lớp được tạo bởi lifecycle/buildpacks có metadata khác với image được build bằng một loạt Dockerfile instructions.

Nếu cài CNB pack CLI, có thể dùng các lệnh inspect/report phù hợp để xem buildpack/process metadata và SBOM của image. Tooling cụ thể phụ thuộc pack version và builder API.

### 18.2. Kiểm tra non-root user

Spring Boot Plugin mô tả image build/run bằng non-root user vì lý do bảo mật. Xem cấu hình:

~~~bash
docker image inspect cnb-demo:1.0.0 --format '{{.Config.User}}'
~~~

Kết quả có thể là một UID không phải 0 tùy builder. Không hardcode một UID cố định trong ứng dụng nếu không cần; hãy kiểm tra file permissions và runtime paths khi app cần ghi dữ liệu.

### 18.3. Kiểm tra kích thước image

~~~bash
docker image ls cnb-demo
docker image inspect cnb-demo:1.0.0 --format '{{.Size}}'
docker system df -v
~~~

Phân biệt:
- Image SIZE local thường là uncompressed size.
- Registry truyền compressed blobs.
- Shared/unique size phụ thuộc những image khác trên daemon.
- Buildpack cache volumes chiếm disk riêng với runtime image.

Không kết luận image nhỏ hơn chỉ vì chọn builder có chữ tiny. So cùng ứng dụng, cùng platform và cùng JRE/dependency policy; builder tiny có thể không chứa component mà app cần hoặc cần buildpack khác.

## 19. Tự động build image trong Maven lifecycle

Nếu tổ chức muốn **mvn package** tự tạo image, bind **build-image-no-fork** vào phase package:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>build-image-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Khi đó:

~~~bash
./mvnw package
~~~

sẽ chạy package và goal build image theo execution. Điều này thuận tiện cho CI nhưng cũng có nghĩa mọi lượt package local có thể cần Docker daemon, pull builder và chạy buildpacks. Nếu developer không có Docker, phase package có thể thất bại.

Có thể dùng profile Maven riêng cho container build:

~~~xml
<profiles>
    <profile>
        <id>container-image</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <phase>package</phase>
                            <goals>
                                <goal>build-image-no-fork</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Sau đó gọi:

~~~bash
./mvnw -Pcontainer-image package
~~~

Đây là lựa chọn tổ chức build; không phải mọi project cần profile. Đảm bảo không khai báo plugin executions trùng lặp ở nhiều parent/profile làm image build nhiều lần ngoài ý muốn.

## 20. Exclude/include dependencies

Khi build image, Spring Boot Plugin đóng gói ứng dụng theo các quy tắc repackage. Một số dependencies như **spring-boot-devtools** và **spring-boot-docker-compose** được loại mặc định; có thể điều chỉnh qua cấu hình plugin nếu project thật sự cần.

Từ Spring Boot 3.5.7, tham số **includeOptional** được hỗ trợ và mặc định true trong build-image goal. Nếu ứng dụng có dependency optional mà cần đưa vào image, kiểm tra effective POM và hành vi phiên bản plugin. Không tự loại một dependency chỉ vì nó làm image lớn hơn; application có thể chỉ dùng nó ở một endpoint hoặc feature hiếm.

Các tham số khác gồm **excludes**, **excludeGroupIds**, **includeSystemScope**, **classifier** và **sourceDirectory**. Chỉ thay đổi khi đã hiểu Maven dependency graph và artifact mà build-image đang đọc.

## 21. Lỗi thường gặp khi chạy spring-boot:build-image

| Lỗi hoặc triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Cannot connect to Docker daemon | Docker daemon/context chưa chạy hoặc Maven dùng context khác | docker info, docker context show, DOCKER_HOST/DOCKER_CONTEXT |
| Error response from daemon | Docker Engine/permissions/network | Docker logs, daemon status, user permissions |
| Pull access denied for builder | Builder image private hoặc sai tên/tag | builder reference, builderRegistry, Docker login |
| Run image pull fails | Run image registry/private credentials hoặc network | Builder metadata, registry credentials, pullPolicy |
| No buildpack groups passed detection | Builder không có buildpack phù hợp hoặc app layout sai | Builder contents, buildpack order, artifact path |
| Buildpack detect failed | Không nhận diện được source/artifact | Maven package, main class, sourceDirectory |
| Build phase failed | JDK download, dependency resolve, proxy hoặc buildpack error | Verbose logs, BP_ variables, network/proxy |
| Export phase failed | Registry/daemon/storage/cache issue | Docker daemon, disk, registry, lifecycle logs |
| Java version không đúng | Compiler config và BP_JVM_VERSION khác nhau | POM properties, buildpack environment, SBOM |
| Image build thành công nhưng container exit | Runtime config, port, Spring bean hoặc missing dependency | docker run, logs, inspect state |
| Container chạy nhưng endpoint fail | Port mapping, security, app bind hoặc chưa ready | docker ps, logs, curl, Actuator readiness |
| Image size quá lớn | Builder/run image hoặc dependency layers không phù hợp | docker image inspect/history, SBOM, builder |
| Build chậm mọi lần | pullPolicy ALWAYS, cache bị đổi tên hoặc cleanCache bật | pull policy, cache volumes, image name |
| CI không dùng được cache | Docker daemon/runner ephemeral hoặc cache volume không persist | Runner lifecycle, cache storage policy |
| Publish bị denied | publishRegistry chưa xác thực hoặc image path sai | image name, Docker credential helper, registry ACL |
| TLS handshake failed | CA/certificate hoặc proxy TLS | Docker cert path, trusted CA, proxy config |
| Platform mismatch | Builder/run image không hỗ trợ target architecture | imagePlatform và builder metadata |
| Permission denied khi app chạy | Non-root user không có quyền ghi path | Container user, volume/file permissions |
| Maven package build image hai lần | build-image và build-image-no-fork bị bind trùng | Effective POM và plugin executions |

### 21.1. Chẩn đoán theo thứ tự

1. Chạy **docker info** để xác nhận daemon.
2. Xác nhận Maven build/package và artifact đầu vào.
3. Xác nhận builder image có thể pull và đúng architecture.
4. Kiểm tra buildpack detection.
5. Đọc log của buildpacks để tìm dependency/JDK/proxy issue.
6. Kiểm tra export/cache/registry.
7. Nếu image tạo xong, kiểm tra Docker inspect và logs lúc runtime.
8. Gọi HTTP readiness/endpoint sau khi container start.

Không sửa POM hoặc đổi builder trước khi biết lỗi nằm ở daemon, detection, build, export hay runtime.

## 22. Build trong CI/CD

Một pipeline cơ bản:

~~~text
Checkout source commit
        |
        v
Maven clean verify
        |
        v
spring-boot:build-image
        |
        v
Inspect image name/platform/digest
        |
        v
Run container smoke test
        |
        v
Security scan + SBOM + policy gates
        |
        v
Publish to registry
        |
        v
Deploy immutable image digest
~~~

Nên tách **build image local** và **publish** thành bước có chủ đích. Chỉ bật publish sau khi image đã vượt tests/scan và target registry/tag đã được xác nhận.

### 22.1. Dùng version và commit tags

Một image có thể có tag version:

~~~text
registry.example.com/team/cnb-demo:1.0.0
~~~

và tag commit:

~~~text
registry.example.com/team/cnb-demo:git-<short-commit>
~~~

Đây là ví dụ naming policy, không phải tag thực tế. Tránh chỉ dùng latest làm deployment reference. Lưu digest mà registry trả về và dùng digest trong manifest triển khai khi cần bảo đảm chính xác image content.

### 22.2. Builder versions trong pipeline

Pin builder/run image versions hoặc digest trong pipeline để build có thể kiểm soát. Khi nâng builder:
- Đọc release notes của builder và buildpacks.
- Xác nhận OS distribution/base image thay đổi.
- Kiểm tra JDK/JRE provider/patch.
- Build lại và so size/startup/health.
- Chạy security scan/SBOM.
- Rollout qua staging trước khi thay đổi production.

Tag latest giúp lấy builder mới nhưng cũng làm cùng commit có thể tạo image khác ở lần build khác. Đây là quyết định freshness so với reproducibility; policy release nên nêu rõ.

### 22.3. Build cache trên runner ephemeral

Nếu CI tạo Docker daemon mới mỗi job, named volumes cache mặc định có thể mất sau job. Khi đó buildpacks phải tải/khôi phục lại nhiều dependencies và thời gian build tăng. Có thể:
- Dùng builder/daemon bền vững với policy cách ly phù hợp.
- Quản lý build/launch cache volumes theo project.
- Dùng registry/cache mechanism được nền tảng hỗ trợ.
- Ghi nhận cache hit/miss và không xóa cache vô điều kiện.

Không dùng chung cache giữa các project không tin cậy nếu chưa đánh giá isolation và lifecycle.

## 23. Buildpacks, SBOM và bảo mật

Buildpacks tạo image có metadata về buildpacks/dependencies; tùy builder/platform, có thể cung cấp SBOM và BOM layers. Đây là đầu vào hữu ích cho:
- Dependency inventory.
- Vulnerability scanning.
- Xác minh JDK/JRE version.
- Truy vết builder/buildpack versions.
- Audit image provenance.

Tuy nhiên **có SBOM không có nghĩa image đã an toàn**. Cần quét CVEs, kiểm tra base image patch status, xác thực buildpack source và review dependency licenses theo policy.

### 23.1. Non-root runtime

Spring Boot Plugin mô tả image được build/run dưới non-root user theo CNB security model. Điều này giảm quyền của ứng dụng so với root, nhưng vẫn cần:
- Cấu hình volumes có owner/permissions đúng.
- Không ghi vào filesystem paths không writable.
- Không expose actuator details/secrets.
- Giới hạn Linux capabilities và network permissions theo môi trường.
- Dùng secrets từ orchestrator/secret manager.

### 23.2. Builder là một thành phần phần mềm cần tin cậy

Builder chứa lifecycle và buildpacks, tức là code thực thi trong quá trình build. Hãy:
- Dùng builder từ nguồn được phê duyệt.
- Pin version/digest.
- Xem buildpack IDs/versions.
- Quản lý quyền truy cập registry.
- Không cho build untrusted pull request truy cập publish credentials.
- Tách credentials build-time khỏi runtime secrets.

Một custom builder có thể cần cấu hình trust riêng; không mặc định builder mới là đáng tin chỉ vì nó tạo được image.

## 24. So sánh buildpacks với Dockerfile trong dự án thật

| Câu hỏi | CNB với build-image | Dockerfile |
| --- | --- | --- |
| Có cần viết lệnh copy JAR không? | Không trong trường hợp chuẩn | Có |
| Có cần chọn JRE? | Buildpack/provider xử lý theo config | Dockerfile/base image do đội chọn |
| Có thể tùy chỉnh OS packages? | Qua buildpack/builder/extension | Qua Dockerfile trực tiếp |
| Có build layers/cache? | Có, qua lifecycle/buildpack layers | Có, theo instructions và build cache |
| Có thể kiểm soát entrypoint? | Qua process type/buildpack config | Qua ENTRYPOINT/CMD |
| Tính minh bạch các bước OS | Qua builder/buildpack metadata/logs | Trực tiếp trong Dockerfile |
| Dùng cho ứng dụng Java thông thường | Rất phù hợp | Phù hợp |
| Tùy biến sâu môi trường OS | Cần builder/custom buildpack | Thường trực tiếp hơn |

Không có lựa chọn đúng cho mọi team. CNB phù hợp với các ứng dụng theo chuẩn và muốn giảm boilerplate; Dockerfile phù hợp khi cần chỉ định chi tiết môi trường image. Cả hai đều cần tests, image scans, SBOM, health checks và deployment policy.

## 25. Bài tập thực hành có đáp án

**Câu 1.** Goal spring-boot:build-image có cần chạy docker build với Dockerfile không?

**Đáp án:** Không. Goal dùng Cloud Native Buildpacks để tạo OCI image. Docker daemon vẫn cần thiết trong workflow Spring Boot 3.5 mặc định.

**Câu 2.** Builder và run image có cùng vai trò không?

**Đáp án:** Không. Builder cung cấp buildpacks, lifecycle và build-time environment; run image làm base cho image ứng dụng khi chạy.

**Câu 3.** Vì sao builder có thể chứa JDK/tooling trong khi runtime image chỉ có JRE?

**Đáp án:** Build-time base và runtime base là hai môi trường khác nhau. Builder cần công cụ để build; run image chỉ cần những thành phần cần thiết để chạy ứng dụng.

**Câu 4.** Vì sao lệnh trực tiếp dùng build-image còn lifecycle binding dùng build-image-no-fork?

**Đáp án:** build-image fork Maven lifecycle để bảo đảm package đã chạy. build-image-no-fork tránh fork lại khi goal được gắn vào lifecycle.

**Câu 5.** Sau build-image, image có tự động push lên registry không?

**Đáp án:** Không. publish mặc định false. Cần bật publish và cung cấp image name/registry credentials phù hợp.

**Câu 6.** BP_JVM_VERSION và JAVA_TOOL_OPTIONS khác nhau thế nào?

**Đáp án:** BP_JVM_VERSION cấu hình Java được cài trong quá trình build image. JAVA_TOOL_OPTIONS truyền flags cho JVM lúc container chạy.

**Câu 7.** Tại sao đổi image tag có thể làm mất cache?

**Đáp án:** Cache volumes mặc định được đặt tên dựa trên full image name. Khi tên/tag thay đổi liên tục, plugin có thể dùng volume cache khác.

**Câu 8.** cleanCache=true có nên bật trong mọi lần CI build?

**Đáp án:** Không. Nó xóa cache trước build và có thể làm build chậm. Chỉ bật khi cần làm sạch/điều tra cache.

**Câu 9.** createdDate cố định có đảm bảo reproducible image không?

**Đáp án:** Không. Còn phải pin builder/run images, buildpacks, dependencies, platform và những đầu vào khác.

**Câu 10.** Image build thành công nhưng container không trả HTTP response, cần làm gì?

**Đáp án:** Kiểm tra docker ps, inspect State, logs, port mapping, Spring configuration và readiness. Build success không chứng minh runtime success.

## 26. Checklist trước khi phát hành image

- [ ] Maven build/tests PASS trên source commit đã chốt.
- [ ] Spring Boot Maven Plugin version phù hợp với project.
- [ ] Docker daemon/context mà Maven sử dụng đã được xác minh.
- [ ] Builder và run image đến từ nguồn được phê duyệt, có version/digest policy.
- [ ] Java compatibility và BP_JVM_VERSION thống nhất.
- [ ] Image name, version tag và target registry đúng.
- [ ] Buildpack detect/build/export thành công.
- [ ] Build cache policy phù hợp với CI runner.
- [ ] Image được tạo local trước khi publish; publish chỉ bật khi đã duyệt.
- [ ] Builder registry credentials và publish credentials được tách rõ.
- [ ] Không hardcode secrets hoặc embed credentials vào image.
- [ ] Image chạy non-root và có file permissions phù hợp.
- [ ] Docker inspect xác nhận platform, image ID/digest và runtime config.
- [ ] Container smoke test PASS, HTTP endpoint và readiness PASS.
- [ ] SBOM/security scan/license checks theo policy đã PASS.
- [ ] createdDate/builder/buildpack/dependency inputs được quản lý nếu cần reproducibility.
- [ ] Registry digest được lưu trong release record và dùng cho deployment cần immutable identity.
- [ ] Cache volumes và workspace được quản lý; không xóa cache của project khác.

## 27. Kết luận

Maven goal **spring-boot:build-image** dùng **Cloud Native Buildpacks** để biến Spring Boot JAR/WAR thành OCI image. Plugin điều phối builder và buildpacks, tạo runtime layers, xuất image vào Docker daemon và có thể publish lên registry khi được bật.

Quy trình cần nhớ:

~~~text
Maven project + spring-boot:build-image
                   |
                   v
             Docker daemon
                   |
                   v
          CNB builder + lifecycle
                   |
                   v
           Detect buildpacks
                   |
                   v
          Restore / Build layers
                   |
                   v
             Export OCI image
                   |
                   v
          docker image inspect
                   |
                   v
             docker run
                   |
                   v
        HTTP health + smoke tests
                   |
                   v
             Publish / Deploy
~~~

Hiểu đúng **builder**, **run image**, **buildpacks**, **cache** và **registry publishing** giúp bạn kiểm soát image thay vì xem build-image như một lệnh tự động không cần hiểu. Với release, hãy pin những đầu vào quan trọng, kiểm tra non-root runtime, smoke test image thật và triển khai bằng digest đã xác minh.

## 28. Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 Maven Plugin — Packaging OCI Images, build-image goal, Docker daemon, builder/run image, publish và cache: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Cloud Native Buildpacks — What is a builder?: https://buildpacks.io/docs/for-app-developers/concepts/builder/
- Cloud Native Buildpacks — What happens during build?: https://buildpacks.io/docs/for-app-developers/concepts/build/
- Cloud Native Buildpacks — Lifecycle Create (analyze/detect/restore/build/export): https://buildpacks.io/docs/for-platform-operators/concepts/lifecycle/create/
- Cloud Native Buildpacks — Build reproducibility: https://buildpacks.io/docs/for-app-developers/concepts/reproducibility/
- Paketo — Configure Paketo Buildpacks, build-time/runtime environment and bindings: https://paketo.io/docs/howto/configuration/
- Paketo — Java Buildpack, JVM version/type and runtime options: https://paketo.io/docs/buildpacks/language-family-buildpacks/java/
- Docker — Docker CLI configuration and contexts: https://docs.docker.com/engine/manage-resources/contexts/
- Docker — Image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Docker — Image history: https://docs.docker.com/reference/cli/docker/image/history/
- Docker — Container run: https://docs.docker.com/reference/cli/docker/container/run/
