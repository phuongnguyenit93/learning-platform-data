# Kiểm tra kích thước image, nội dung lớp và khả năng khởi động

## 1. Tại sao kiểm tra Docker image không dừng ở docker build?

Trong ứng dụng Spring Boot, Dockerfile có thể build thành công nhưng image vẫn quá lớn, đóng gói thiếu JAR, chứa dữ liệu không nên có hoặc không thể phục vụ HTTP request. Vì thế một quy trình QA phải trả lời ba câu hỏi khác nhau:

1. **Kích thước image:** tổng số bytes của image là bao nhiêu; phần nào là Java runtime, phần nào là ứng dụng và thư viện?
2. **Nội dung lớp:** Docker image có đúng filesystem layers và runtime files dự kiến không; lớp dependencies có được cache lại khi chỉ sửa mã ứng dụng?
3. **Khả năng khởi động:** container có chạy đúng Java, vào Spring context, mở cổng và trả HTTP health/endpoint trong một deadline không?

Lệnh **docker build** chỉ xác minh image có thể được tạo. Lệnh **docker run -d** trả container ID nhưng có thể Java crash ngay sau đó. Lệnh **docker image ls** báo SIZE nhưng không chứng minh một servlet đã phục vụ request. Do đó cả ba nhóm kiểm tra phải được làm độc lập.

Bài này thuộc chủ đề **Dockerfile** trong Spring Boot Build Tooling Packaging, dùng Java 17/Spring Boot 3.5 minh họa, có ví dụ Maven/Gradle, hai Dockerfile và các lệnh QA chạy trên Linux hoặc Windows.

## 2. Khái niệm image, container và layer

**Image** là một artifact có cấu hình (ENTRYPOINT, USER, WORKDIR, EXPOSE...) và tập filesystem layers chỉ đọc. **Container** là một instance có process, network, runtime state, log và writable filesystem layer. Một image có thể tạo nhiều containers.

~~~text
Source + Maven/Gradle
         |
         v
Spring Boot executable JAR
         |
         v
Dockerfile + docker build
         |
         v
Image filesystem layers + config
         |
         v
docker run -> Container -> Java process -> Spring Boot
         |
         v
HTTP request + health/readiness
~~~

**Spring Boot layer** và **Docker image layer** không giống nhau. Spring Boot Maven/Gradle plugin có thể tạo file **BOOT-INF/layers.idx** với bốn nhóm:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Spring Boot 3.5 dùng **spring-boot-jarmode-tools**, có thể gọi:

~~~bash
java -Djarmode=tools -jar app.jar list-layers
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
~~~

Lệnh extract tạo các thư mục theo nhóm **Spring Boot**, nhưng **chưa tạo image layers**. Khi Dockerfile chạy những lệnh **COPY --from=extractor** riêng, Docker mới sinh các filesystem layers tương ứng.

Không xem **RootFS.Layers** trong Docker inspect như danh sách tên của **BOOT-INF/layers.idx**. Một bên là nội dung của image filesystem, bên kia là metadata phân loại file trong Java archive.

## 3. Những kích thước dễ gây nhầm lẫn

| Giá trị | Lệnh | Phản ánh |
| --- | --- | --- |
| **Image SIZE** | docker image ls | Tổng kích thước uncompressed của filesystem layers ở image/platform local |
| **Image .Size** | docker image inspect | Bytes của image nếu engine/image store cung cấp trường đó |
| **Shared / Unique** | docker system df -v | Dung lượng lớp dùng chung và riêng giữa các image trên host |
| **BuildKit cache** | docker buildx du | Dung lượng build cache records của builder |
| **Registry compressed blobs** | Registry manifest/OCI tooling | Bytes nén cần upload/download khi không có cache |
| **Container writable layer** | docker inspect --size | Dữ liệu ghi thêm bởi một container, không phải kích thước image |

Đừng báo **docker image ls SIZE = dung lượng phải tải trên mạng**. Docker registry lưu nén các blobs, client có thể có layers sẵn; multi-platform tag cũng có thể trỏ tới các platform variants khác nhau.

Đừng cộng mọi hàng của **docker image ls** để tìm disk usage riêng: hai image cùng dùng base JRE có thể share layers. **docker system df -v** giúp xem shared/unique storage.

**docker buildx du** lại không đo kích thước image runtime; nó đo records cache của builder. Một cache báo 4GB không có nghĩa Docker image bạn phát hành nặng 4GB.

## 4. Điều kiện cho một phép so sánh đúng

Để so hai Dockerfiles, cần giữ:
- Cùng Git commit và cùng executable Boot JAR.
- Cùng Java target, Spring Boot/plugin versions.
- Cùng JRE base image hoặc pinned digest.
- Cùng OS/CPU architecture, ví dụ linux/amd64.
- Cùng Docker Engine/BuildKit builder và cache policy.
- Cùng CPU/memory limits khi kiểm tra thời gian startup.
- Cùng health endpoint và test suite.

Kiểm tra môi trường:

~~~bash
java -version
docker version
docker info
docker buildx version
~~~

Nếu Docker CLI không kết nối được daemon, cần xử lý quyền/dịch vụ theo chính sách của máy. Không xóa Docker caches/images của các dự án khác chỉ để lấy một số đo cold.

Trong production, nên pin digest của base image được phép dùng và theo dõi security patches. Ví dụ dùng **eclipse-temurin:17-jre** để dễ học, không khẳng định đây luôn là image nhỏ nhất hoặc an toàn nhất.

## 5. Project Java 17/Spring Boot để thử image thật

Chúng ta dùng một HTTP endpoint đơn giản, có Actuator readiness và JUnit test. Ví dụ sử dụng **Spring Boot 3.5.16** với Java 17. Với dự án mới, hãy dùng nhánh và bản vá hiện được tổ chức hỗ trợ; version ở đây là ví dụ kỹ thuật.

### 5.1. Cấu trúc tệp

~~~text
image-check/
├── pom.xml                       (Maven)
│   hoặc
├── build.gradle                  (Gradle)
├── settings.gradle               (Gradle)
├── mvnw / mvnw.cmd / .mvn/wrapper/...
├── gradlew / gradlew.bat / gradle/wrapper/...
├── Dockerfile.flat
├── Dockerfile.layered
└── src/
    ├── main/
    │   ├── java/com/example/imagecheck/
    │   │   ├── ImageCheckApplication.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/java/com/example/imagecheck/
        └── ProbeControllerTest.java
~~~

Chỉ chọn **Maven hoặc Gradle** trong một project thực. Wrapper scripts phải được tạo bằng Spring Initializr hoặc công cụ Wrapper tương ứng; thêm POM/build.gradle không tự sinh file **mvnw** hoặc **gradlew**.

### 5.2. Main class

Tệp **src/main/java/com/example/imagecheck/ImageCheckApplication.java**:

~~~java
package com.example.imagecheck;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImageCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImageCheckApplication.class, args);
    }
}
~~~

### 5.3. Controller

Tệp **src/main/java/com/example/imagecheck/ProbeController.java**:

~~~java
package com.example.imagecheck;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    @GetMapping("/probe")
    public String probe() {
        return "image-check-ok";
    }
}
~~~

Nếu app thực sự đang phục vụ HTTP, response body của **GET /probe** chính xác là:

~~~text
image-check-ok
~~~

### 5.4. application.properties

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=image-check
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
~~~

**spring-boot-starter-actuator** tạo health endpoints. **management.endpoint.health.probes.enabled=true** cho phép nhóm liveness/readiness khi thử nghiệm ngoài Kubernetes. Khi ứng dụng ready và không có indicator lỗi, **/actuator/health/readiness** thường trả:

~~~json
{"status":"UP"}
~~~

Readiness của Spring Boot không tự xác minh mọi hệ thống bên ngoài; nếu muốn kiểm tra một external dependency, phải cấu hình nhóm health phù hợp và đánh giá rủi ro.

### 5.5. JUnit/MockMvc test

Tệp **src/test/java/com/example/imagecheck/ProbeControllerTest.java**:

~~~java
package com.example.imagecheck;

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
class ProbeControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void probeReturnsExpectedBody() throws Exception {
        mvc.perform(get("/probe"))
                .andExpect(status().isOk())
                .andExpect(content().string("image-check-ok"));
    }
}
~~~

**Lưu ý:** test dùng classpath của Maven/Gradle; nó **không xác nhận Docker image có đủ runtime libraries**. Phải chạy chính image và gửi request ở bước sau.

## 6. Cấu hình Maven tạo executable layered JAR

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
    <artifactId>image-check</artifactId>
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
                    <layers>
                        <enabled>true</enabled>
                    </layers>
                    <includeTools>true</includeTools>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot starter parent cung cấp managed versions và execution **repackage** khi plugin được khai báo. **layers.enabled** tạo metadata lớp; **includeTools** giữ **spring-boot-jarmode-tools** trong executable JAR. Với Spring Boot 3.5, hai thiết lập này đã mặc định bật trong cấu hình phù hợp, nhưng được ghi tường minh để học.

**Không bật <executable>true</executable>** trong Maven cho archive cần jarmode tools: fully executable JAR chứa Unix launch script prefix không tương thích tools mode.

Build:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

Khi tests PASS, Boot JAR thường ở:

~~~text
target/image-check-1.0.0.jar
~~~

Dùng **mvnw.cmd** trên Windows. Nếu custom finalName/classifier, phải sửa đường COPY sau đây theo đúng artifact thật.

## 7. Cấu hình Gradle tương đương

Nếu dùng Gradle, **không cần pom.xml** ở phần trên. Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'image-check'
~~~

Tệp **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    layered {
        enabled = true
    }
    includeTools = true
}
~~~

Build với Gradle Wrapper tương thích (ví dụ Gradle 8.14 trong dải Spring Boot 3.5):

~~~bash
./gradlew --version
./gradlew clean test bootJar
~~~

Output mặc định:

~~~text
build/libs/image-check-1.0.0.jar
~~~

**bootJar** khác plain **jar** task. Nếu dùng Gradle, thay mọi đường **COPY target/image-check-1.0.0.jar** trong Dockerfiles bằng **COPY build/libs/image-check-1.0.0.jar**. Không chạy cả Maven và Gradle rồi trộn artifacts của hai project.

## 8. Dockerfile.flat: copy nguyên Boot JAR

Tạo **Dockerfile.flat**:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /application

COPY target/image-check-1.0.0.jar application.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

- Base JRE đủ chạy Java, không cần chứa Maven, Gradle hoặc javac.
- **COPY** chuyển executable Spring Boot JAR vào runtime.
- **USER 10001:10001** dùng numeric non-root account; cần xác minh các file/working directory cho phép user đọc.
- **EXPOSE 8080** chỉ khai báo metadata, không tự publish cổng host.
- **ENTRYPOINT** dùng exec-form để Java nhận signals trực tiếp hơn so với wrapper shell tùy tiện.

Build sau khi Maven clean verify thành công:

~~~bash
docker build -f Dockerfile.flat -t image-check:flat .
~~~

Cách này đơn giản. Nhưng khi chỉ sửa một controller, byte của original uber JAR có thể đổi hoàn toàn; Docker layer chứa application.jar phải được tạo lại, dù third-party dependencies không đổi.

## 9. Dockerfile.layered: COPY theo các lớp Spring Boot

Tạo **Dockerfile.layered**:

~~~dockerfile
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /builder

COPY target/image-check-1.0.0.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /builder/extracted/dependencies/ ./
COPY --from=extractor /builder/extracted/spring-boot-loader/ ./
COPY --from=extractor /builder/extracted/snapshot-dependencies/ ./
COPY --from=extractor /builder/extracted/application/ ./

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Trong extractor stage, **jarmode tools** chia Boot executable archive thành folders. Runtime stage chỉ copy files đã trích; original full uber JAR không cần xuất hiện trong image cuối.

Bốn thư mục mặc định:
- **dependencies**: third-party dependencies ổn định.
- **spring-boot-loader**: Spring Boot Loader classes.
- **snapshot-dependencies**: dependencies SNAPSHOT, nếu có.
- **application**: compiled application/resources và local project components.

Trong runtime layout hiệu quả, Spring Boot tools tạo **application.jar** nhỏ và các JAR files dưới **lib/**. Bốn COPY gộp nội dung vào **/application**; chỉ copy riêng **extracted/application/** thường không đủ để chạy.

Build:

~~~bash
docker build -f Dockerfile.layered -t image-check:layered .
~~~

Nếu định nghĩa custom layer names, phải thay các COPY theo danh sách **list-layers** thực tế, không mặc định luôn có đúng bốn lớp. Thứ tự ổn định trước/thay đổi thường xuyên sau tạo cơ hội tái sử dụng cache, **không đảm bảo image SIZE nhỏ hơn**.

### 9.1. Kiểm tra Spring Boot layers trước Docker build

~~~bash
java -Djarmode=tools -jar target/image-check-1.0.0.jar list-layers
java -Djarmode=tools -jar target/image-check-1.0.0.jar extract --layers --destination extracted
~~~

Output list-layers mặc định dự kiến:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Các lệnh trên **không chạy Application.main()** và không gọi JUnit; chúng làm việc với archive đã build. **-Djarmode=tools** phải đứng trước **-jar**, nếu không JVM không nhận được JarMode system property đúng thời điểm.

## 10. Kiểm tra kích thước image bằng docker image ls

Khi đã build cả hai tags:

~~~bash
docker image ls image-check
~~~

Bảng dưới đây chỉ là **minh họa**, không phải kết quả thực tế:

~~~text
REPOSITORY    TAG       IMAGE ID        SIZE
image-check   flat      <image-id-1>     238MB
image-check   layered   <image-id-2>     239MB
~~~

Hai image có thể có tổng dung lượng gần nhau vì cùng chứa JRE và dependencies, chỉ khác layout. Từ bảng ví dụ không thể kết luận layered tệ hơn: mục tiêu chính có thể là giảm bytes cần push/pull lại khi source code thay đổi.

Dùng output có format để ghi log:

~~~bash
docker image ls image-check --format 'table {{.Repository}}:{{.Tag}}	{{.ID}}	{{.Size}}'
~~~

Để lấy số bytes:

~~~bash
docker image inspect image-check:flat --format '{{.Size}}'
docker image inspect image-check:layered --format '{{.Size}}'
~~~

**.Size** có mặt trên nhiều Docker engine/image stores, nhưng có thể không khả dụng giống nhau ở mọi chế độ; nếu field vắng, dùng thông tin từ **docker image ls** và inspection tương thích engine thay vì tự thay số 0.

**Đơn vị:** 1 MiB = 1.048.576 bytes; 1 MB = 1.000.000 bytes. Khi so, luôn đổi về cùng đơn vị.

### 10.1. Ghi đúng platform và image identity

~~~bash
docker image inspect image-check:layered --format '{{.Id}}'
docker image inspect image-check:layered --format '{{.Os}}/{{.Architecture}}'
docker image inspect image-check:layered --format '{{json .Config.Entrypoint}}'
docker image inspect image-check:layered --format '{{.Config.User}}'
~~~

Nếu A được build cho linux/amd64 còn B cho linux/arm64, có thể chứa JRE khác kích thước. Đừng so chênh lệch đó như kết quả tối ưu Dockerfile. Image tag có thể bị ghi đè sau rebuild; lưu image ID/digest để không so nhầm phiên bản.

## 11. Kiểm tra Docker filesystem layers bằng history

~~~bash
docker image history image-check:flat
docker image history image-check:layered
docker image history --no-trunc image-check:layered
~~~

Để tập trung instruction và layer size:

~~~bash
docker image history --format 'table {{.CreatedBy}}	{{.Size}}' image-check:layered
~~~

Trong layered image bạn cần tìm những **COPY --from=extractor** cho dependencies, loader, snapshot dependencies và application, cũng như những entries của base image. Docker history hiển thị entries **mới nhất trước**.

Một số entries như **USER**, **WORKDIR**, **EXPOSE**, **ENTRYPOINT** thay image config nhưng không nhất thiết tạo filesystem bytes, nên có thể hiện **0B**.

### 11.1. RootFS.Layers không phải tên các lớp Spring Boot

~~~bash
docker image inspect image-check:layered --format '{{json .RootFS.Layers}}'
~~~

**RootFS.Layers** thường là danh sách uncompressed filesystem **diff IDs**. Chúng không phải registry compressed blob digests, không phải tên lớp từ layers.idx và không có quan hệ 1:1 với mọi history entry 0B.

Do đó history có 14 hàng mà RootFS.Layers có 8 phần tử không tự là lỗi. Những metadata-only instructions có thể không sinh filesystem layer.

### 11.2. Khi nào layered Dockerfile thực sự hữu ích?

Nếu developer chỉ sửa **ProbeController.java**:
- Flat image: original JAR đổi, layer COPY của JAR thường bị invalidated.
- Layered image: các thư mục dependencies/loader có thể giữ cùng nội dung và được cache; application layer thay đổi.
- Nếu Spring Boot/dependency version đổi, các lớp thư viện tương ứng cũng có thể đổi.

Vì vậy hãy so **rebuild time, cache hits, bytes upload/pull**, không chỉ image SIZE. Nếu chạy CI trên runner hoàn toàn mới không có cache, bước extraction có thể thêm overhead mà không mang lợi ích.

## 12. Dung lượng chia sẻ và cache disk usage

~~~bash
docker system df
docker system df -v
docker buildx du
~~~

**docker system df -v** giúp xem phần SHARED SIZE/UNIQUE SIZE của local images. Khi cả flat và layered image đều dựa trên cùng base JRE, chúng có thể share base layers.

**docker buildx du** cho biết BuildKit builder cache. Con số này có thể lớn hơn nhiều image SIZE vì chứa snapshots, contexts và intermediate build records. Không coi nó là dung lượng runtime image.

**Không tự dùng docker system prune -a hoặc docker builder prune trên máy dùng chung**. Những lệnh này có thể xóa images/cache của dự án khác, làm chậm những lượt build sau và làm lệch benchmark. Dùng runner/builder riêng hoặc chỉ dọn tài nguyên job đã tạo theo chính sách.

## 13. Kiểm tra file thực trong runtime image

Image history không liệt kê đầy đủ mọi file. Khi base image có shell, dùng ENTRYPOINT override để nhìn filesystem:

~~~bash
docker run --rm --entrypoint sh image-check:layered   -c 'ls -la /application; ls /application/lib | head -n 20'
~~~

Flat image:

~~~bash
docker run --rm --entrypoint sh image-check:flat   -c 'ls -lh /application/application.jar'
~~~

Layered image cần có **/application/application.jar**, thư mục **lib/** và những files phụ trợ của extracted layout. Flat image chỉ cần original Boot JAR và Java runtime. Không xóa lib/ để làm nhỏ image, vì runtime sẽ có thể mất classes.

Đây chỉ là **filesystem inspection**, chưa phải kiểm tra khởi động Java. Trên distroless image thường không có **sh**; dùng builder/debug stage phù hợp thay vì thêm shell vào production chỉ để kiểm tra.

### 13.1. Kiểm tra cấu hình image

~~~bash
docker image inspect image-check:layered --format '{{json .Config.Entrypoint}}'
docker image inspect image-check:layered --format '{{.Config.WorkingDir}}'
docker image inspect image-check:layered --format '{{.Config.User}}'
docker image inspect image-check:layered --format '{{json .Config.ExposedPorts}}'
~~~

Với Dockerfile mẫu:
- Entrypoint dùng **java -jar application.jar**.
- WorkingDir là **/application**.
- User là **10001:10001**.
- ExposedPorts có **8080/tcp** metadata.

**EXPOSE không publish cổng host.** Nếu cần truy cập service từ host, phải dùng **-p** hoặc network/orchestrator config thích hợp.

### 13.2. Tìm files không nên có

Runtime image thông thường không cần:
- Git repository, Java source/test output, Maven/Gradle caches;
- private keys, access tokens, environment files chứa secrets;
- compiler toolchain hoặc package manager cache không dùng runtime;
- logs cũ và build temporary files.

Khi inspection, không xuất raw environment hoặc contents của credentials ra logs công khai. Lưu ý image history có thể còn dữ liệu từ một layer cũ dù final filesystem đã xóa file. Nếu có rò rỉ secret, phải xử lý rotate/revoke và rebuild an toàn.

## 14. Startup: container ID không bằng Spring Boot ready

Chạy layered image trên localhost:

~~~bash
docker run -d --name image-check-smoke   -p 127.0.0.1:18080:8080   image-check:layered
~~~

Giải thích:
- **-d** chạy detached.
- **--name** giúp dễ inspect/log.
- **-p 127.0.0.1:18080:8080** publish host loopback 18080 vào container port 8080, hạn chế exposure trong bài test.
- Java process khởi động theo ENTRYPOINT.

Sau khi Docker trả container ID, **vẫn phải xem process state**:

~~~bash
docker ps --filter "name=image-check-smoke"
docker ps -a --filter "name=image-check-smoke"
docker inspect --type container image-check-smoke --format '{{.State.Status}}'
~~~

Khi container exited/restarting:

~~~bash
docker inspect --type container image-check-smoke   --format 'exit={{.State.ExitCode}} oom={{.State.OOMKilled}}'
docker logs --tail 80 image-check-smoke
~~~

**OOMKilled=true** là một dấu hiệu memory exhaustion, cần kiểm tra giới hạn container/heap/native memory. **ExitCode=0** có thể hợp lý với batch job, nhưng với HTTP service cần chạy liên tục thì exited không đạt mục tiêu serve requests.

### 14.1. Đọc logs theo tầng

| Triệu chứng | Tầng kiểm tra |
| --- | --- |
| Unable to access jarfile application.jar | COPY/WORKDIR/ENTRYPOINT |
| UnsupportedClassVersionError | JRE runtime và Java target |
| NoClassDefFoundError / ClassNotFoundException | lib/ hoặc COPY layer thiếu |
| BeanCreationException | Spring DI/config |
| Port bind error | server.port hoặc networking |
| OOMKilled | memory limit và JVM memory |
| Connection refused | Server chưa ready, process crash hoặc port mapping |
| 404 từ actuator readiness | Dependency Actuator, probe setting, base path |

Đừng thay build.gradle/pom.xml theo cảm tính khi lỗi thực là cổng host hoặc thiếu secret tại runtime; cũng đừng đổi Spring properties khi image thiếu application.jar.

## 15. Smoke test HTTP + Spring Boot Actuator

Từ terminal host:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/probe
~~~

Body chính xác của ví dụ khi thành công:

~~~text
image-check-ok
~~~

Kiểm tra Actuator:

~~~bash
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health/liveness
curl --fail --silent --show-error http://127.0.0.1:18080/actuator/health/readiness
~~~

Khi sẵn sàng, readiness thường trả:

~~~json
{"status":"UP"}
~~~

**Liveness** là khả năng tiến trình tiếp tục hoạt động; không nên gắn thẳng với lỗi DB ngoài để tránh restart tất cả pods khi DB outage. **Readiness** là khả năng nhận traffic dựa trên Spring ApplicationAvailability và health indicators được cấu hình; không mặc định kiểm mọi external dependency.

Nếu Spring Security chặn health, kiểm tra HTTP authentication và exposure policy, **không mở toàn bộ Actuator endpoints công khai** chỉ để test thuận tiện.

### 15.1. Retry có deadline, không sleep cố định

Java/Spring Boot cần thời gian tạo ApplicationContext. Lệnh docker run -d có thể trả về trước readiness nhiều giây. Một script CI phải:
1. Gọi endpoint nhiều lần trong một deadline hữu hạn.
2. Chỉ PASS khi HTTP response và status đáp ứng.
3. Khi timeout, ghi docker logs/State.ExitCode rồi FAIL.
4. Dọn container test sau khi hoàn tất.

Không dùng duy nhất **sleep 2** rồi kết luận mọi app startup chậm hơn 2 giây đều không deploy được.

## 16. Bash smoke script có cleanup

Dùng trên CI Linux runner dành riêng cho test, tạo **smoke.sh**:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

name="image-check-ci-smoke"
base="http://127.0.0.1:18080"

docker run -d --name "$name"   -p 127.0.0.1:18080:8080 image-check:layered >/dev/null

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ready=0
for attempt in $(seq 1 30); do
  if curl --fail --silent "$base/actuator/health/readiness" |
     grep -q '"status":"UP"'; then
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "FAIL: readiness not UP"
  docker ps -a --filter "name=$name"
  docker logs --tail 100 "$name"
  exit 1
fi

body="$(curl --fail --silent --show-error "$base/probe")"
if [ "$body" != "image-check-ok" ]; then
  echo "FAIL: unexpected response"
  exit 1
fi

echo "PASS: container ready and HTTP probe correct"
~~~

Chạy:

~~~bash
chmod +x smoke.sh
./smoke.sh
~~~

Khi mọi điều kiện đúng, script in:

~~~text
PASS: container ready and HTTP probe correct
~~~

Đây là **expected stdout của ví dụ**, không phải kết quả thực thi trên máy hiện tại. Script cần Bash, Docker, curl, grep và seq. Nó dùng tên/port cố định, chỉ phù hợp với runner riêng không có job trùng. Trong CI song song phải sinh tên/port theo job ID và không xóa nhầm container của người khác.

Script dọn đúng container nó đã tạo; không prune toàn bộ images/cache. Nếu cần deadline dài hơn 30 lần 1 giây, điều chỉnh theo startup SLO và resource limits của tổ chức.

## 17. Dừng container, kiểm tra CPU/RAM và HEALTHCHECK

Với container thủ công:

~~~bash
docker stop --time 15 image-check-smoke
docker ps -a --filter "name=image-check-smoke"
docker rm image-check-smoke
~~~

Dùng **docker stop** để cho ứng dụng cơ hội graceful shutdown, thay vì luôn kill -9. Khi container đang chạy, kiểm tra runtime resource usage:

~~~bash
docker stats --no-stream image-check-smoke
docker inspect --size --type container image-check-smoke
~~~

**docker stats** đo CPU/memory/network; **docker inspect --size** có thể thêm SizeRw/SizeRootFs cho container filesystem. Chúng **không phải image SIZE** và không phải compressed download size.

### 17.1. Không có HEALTHCHECK không đồng nghĩa unhealthy

Hai Dockerfiles trên chưa khai báo HEALTHCHECK, nên Docker không tự đặt container vào trạng thái **healthy**. **.State.Health** có thể không tồn tại hoặc null.

Nếu muốn dùng Docker HEALTHCHECK, phải có một công cụ kiểm tra trong runtime image. Đoạn minh họa **chỉ có tác dụng khi runtime thật đã có curl**:

~~~dockerfile
HEALTHCHECK --interval=30s --timeout=3s   --start-period=40s --retries=3   CMD curl --fail --silent http://127.0.0.1:8080/actuator/health/readiness || exit 1
~~~

Không giả định base eclipse-temurin hoặc distroless có curl. Khi helper không tồn tại, healthcheck FAIL dù web server có thể hoạt động. Có thể dùng Kubernetes HTTP probes hoặc health checker được package có kiểm soát.

Với image đã có HEALTHCHECK:

~~~bash
docker inspect --type container image-check-smoke   --format '{{json .State.Health}}'
~~~

Liveness/readiness của Kubernetes và healthcheck Docker khác cơ chế quản lý. Với startup lâu có thể cần Kubernetes **startupProbe** để không restart container trước khi ready.

## 18. So sánh flat/layered với số liệu minh họa

| Metric | Flat | Layered | Nhận xét |
| --- | ---: | ---: | --- |
| Image uncompressed SIZE | 238 MiB | 239 MiB | Không mặc định layer nhỏ hơn |
| COPY runtime content | Một uber JAR | Bốn nhóm lớp | Cache boundaries khác |
| First image build | 24 s | 29 s | Layered thêm extraction |
| Rebuild khi sửa controller | 12 s | 6 s | Stable dependencies có thể cache hit |
| Readiness time | 4.2 s | 4.0 s | Cần nhiều mẫu để khẳng định |
| /probe | PASS | PASS | Chức năng giống nhau |

**Toàn bộ con số là giả định để diễn giải**. Cùng source, JRE, platform, test conditions và Docker cache policy mới có phép so ý nghĩa.

Ví dụ size tăng:

~~~text
Delta SIZE = 239 - 238 = +1 MiB
Delta% = 1 / 238 * 100% = +0.42%
~~~

Không gọi đó là “giảm size” chỉ vì dùng layered Dockerfile. Nếu thời gian rebuild từ 12 xuống 6 giây, đó là giảm **50%** trong bộ số giả định, nhưng cần đo lặp lại trên CI thật để kết luận.

Để đo từ registry, compressed blobs và layers đã có trên client mới quyết định bytes cần tải. Một tag nhiều architecture có thể trỏ tới nhiều manifests. **docker image ls** ở host linux/amd64 không đại diện cho bytes pull của host linux/arm64.

## 19. PowerShell/Windows Docker Desktop

Docker Desktop có Docker CLI chạy từ PowerShell:

~~~powershell
docker image ls image-check
docker image history image-check:layered
docker image inspect image-check:layered --format '{{.Os}}/{{.Architecture}}'
docker system df -v
~~~

Test container:

~~~powershell
docker run -d --name image-check-ps -p 127.0.0.1:18080:8080 image-check:layered
docker ps -a --filter "name=image-check-ps"
docker logs --tail 60 image-check-ps
~~~

Gọi HTTP:

~~~powershell
(Invoke-WebRequest 'http://127.0.0.1:18080/probe').Content
(Invoke-WebRequest 'http://127.0.0.1:18080/actuator/health/readiness').Content
~~~

Sau đó:

~~~powershell
docker stop image-check-ps
docker rm image-check-ps
~~~

**Invoke-WebRequest** trả response object, dùng **.Content** để xem body. Nếu Docker Desktop đang dùng Linux containers, image base Java 17 vẫn là Linux JRE; không nhầm đó là native Windows executable. Khi dùng Gradle, sửa COPY source path trong Dockerfile thay vì mang PowerShell backslash path vào Linux image.

## 20. Bảng chẩn đoán nhanh

| Lỗi | Hướng điều tra |
| --- | --- |
| Docker COPY không thấy JAR | Maven/Gradle build output path, .dockerignore, context |
| Image quá lớn | Base JDK thay JRE, files dư, history |
| Layered không nhỏ hơn flat | Bình thường nếu cùng runtime files |
| buildx du lớn | BuildKit cache, không phải runtime image |
| history nhiều entries 0B | Metadata entries, không phải mỗi dòng có filesystem bytes |
| Unable to access jarfile | WORKDIR/ENTRYPOINT/COPY sai |
| ClassNotFoundException | lib/ hoặc custom layer bị thiếu |
| UnsupportedClassVersionError | Java runtime quá cũ |
| Docker run -d rồi exited | Đọc logs, State.ExitCode, OOMKilled |
| Port 18080 bận | Chọn port khác và sửa URL curl |
| Container running nhưng curl fail | Startup chưa ready, port mapping, binding, app exception |
| Actuator 404/401 | Thiếu starter-actuator, settings/security |
| Health unhealthy | Check healthcheck command có curl/đúng port |
| Image chạy máy này không chạy máy kia | Architecture/platform, JRE/OS differences |
| Dependency layer không cache được | Build inputs, ordering, new base digest, builder cache policy |
| Docker disk đầy nhưng image SIZE nhỏ | Volumes, containers, builder cache, docker system df |

Dùng logs theo đúng tầng: image build → filesystem layout → Java runtime/classpath → Spring context → networking → readiness → nghiệp vụ.

## 21. Checklist QA trước khi phát hành

- [ ] Java build/test PASS, artifact Boot executable JAR đúng version.
- [ ] Dockerfile COPY đúng file, không bị .dockerignore loại.
- [ ] Cùng base JRE/platform để so flat và layered.
- [ ] Spring Boot layered mode có tools JAR và mọi thư mục lớp được COPY.
- [ ] Đọc docker image ls, image inspect, ghi unit và image ID.
- [ ] Đọc docker image history, RootFS.Layers, phân biệt metadata 0B.
- [ ] Không nhầm Image SIZE với shared/unique disk, cache hoặc registry compressed bytes.
- [ ] Runtime filesystem có application.jar và lib/ nếu dùng layered layout.
- [ ] Không chứa source/test output, build caches, secrets/credentials.
- [ ] WORKDIR, USER, ENTRYPOINT, EXPOSE đúng.
- [ ] Container running, logs không có fatal startup error.
- [ ] GET /probe trả chính xác **image-check-ok**.
- [ ] /actuator/health/readiness báo UP theo deadline.
- [ ] Kiểm tra graceful stop, OOMKilled, CPU/RAM nếu cần.
- [ ] Khi dùng HEALTHCHECK, helper có thật và endpoint phù hợp.
- [ ] Ghi cache state, startup timings và actual image size khi so tối ưu.
- [ ] Ghi source commit, JDK, image digest, platform và security test evidence.
- [ ] Dọn đúng container test, không prune resources của project khác.

## 22. Kết luận

Quy trình Dockerfile QA nên đi theo:

~~~text
Build Spring Boot JAR + tests
              |
              v
docker build flat/layered
              |
              v
docker image ls / inspect -> size + platform
              |
              v
docker history + RootFS.Layers -> layers
              |
              v
Xem runtime application.jar + lib
              |
              v
docker run + ps/inspect/logs
              |
              v
curl /probe + Actuator readiness
              |
              v
stop container + lưu release evidence
~~~

**Image nhỏ không đủ; image có lớp hợp lý cũng chưa đủ.** Artifact chỉ đáng tin khi runtime files đúng, có thể chạy trên platform đích và vượt smoke tests. Spring Boot layer extraction chủ yếu giúp tái sử dụng cache của dependencies, không làm các dependencies cần thiết biến mất.

## 23. Tài liệu tham khảo chính thức

- Docker — Image list và SIZE: https://docs.docker.com/reference/cli/docker/image/ls/
- Docker — Image inspect: https://docs.docker.com/reference/cli/docker/image/inspect/
- Docker — Image history: https://docs.docker.com/reference/cli/docker/image/history/
- Docker — Docker system df: https://docs.docker.com/reference/cli/docker/system/df/
- Docker — Buildx du: https://docs.docker.com/reference/cli/docker/buildx/du/
- Docker — Docker inspect: https://docs.docker.com/reference/cli/docker/inspect/
- Docker — Dockerfile reference: https://docs.docker.com/reference/dockerfile/
- Docker — Build cache optimization: https://docs.docker.com/build/cache/optimize/
- Docker — Multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Spring Boot 3.5 — Dockerfiles with jarmode tools: https://docs.spring.io/spring-boot/3.5/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.5 — Maven packaging: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle packaging: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Actuator health and probes: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
