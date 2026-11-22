# Thử thay đổi mã hoặc dependency để quan sát cache và lớp image Spring Boot

## 1. Mục tiêu và quy tắc thí nghiệm

Bài lab dùng một ứng dụng Spring Boot nhỏ để quan sát bảy bước: build lần đầu, build lại không đổi input, sửa một dòng Java, nâng version dependency, đóng gói JAR thành Docker image nhiều layer, quan sát BuildKit cache và so sánh với Cloud Native Buildpacks (CNB).

Môi trường tham khảo: **Java 17, Spring Boot 3.3.13, Maven Wrapper hoặc Gradle Wrapper, Docker BuildKit**. Spring Boot 3.3.13 yêu cầu Java 17 trở lên, hỗ trợ Maven 3.6.3+ và Gradle 7.5+ thuộc dòng Gradle 7.x/8.x. Hãy dùng wrapper và toolchain đã được dự án pin. Các lệnh là hướng dẫn thực hành, không phải kết quả build đã chạy sẵn.

Mỗi lượt chỉ thay đổi một yếu tố. Giữ nguyên commit, JDK, wrapper, build command, Dockerfile và image base khi so sánh. Ghi lại task/goal thực sự chạy, dependency version được resolve, SHA-256 của JAR, Docker cache lines, image layer diff IDs và response endpoint.

## 2. Mô hình cache và artifact

§§§text
Java source / pom.xml / build.gradle
                 |
                 v
        Maven / Gradle build
          |              |
          v              v
  Dependency cache   Task / incremental state
          |              |
          +-------+------+
                  |
                  v
        Spring Boot executable JAR
                  |
                  v
       Docker BuildKit / CNB builder
          |              |
          v              v
     Build cache     Image layers
          |              |
          +-------+------+
                  |
                  v
          OCI image + container
                  |
                  v
          Runtime response
§§§

Phân biệt ba kết quả:

| Hiện tượng | Ý nghĩa |
| --- | --- |
| **Task/cache hit** | Build tool bỏ qua một phần công việc vì input/output phù hợp với trạng thái hoặc cache key. |
| **Image layer reuse** | Builder dùng lại layer vì instruction và input liên quan không đổi. |
| **Artifact/image thay đổi** | Bytes của JAR hoặc nội dung image khác trước; điều này không tự chứng minh cache hoạt động sai. |

Một build có thể có task UP-TO-DATE nhưng image vẫn thay đổi do base image, metadata hoặc timestamp. Docker có thể cache một RUN dù package repository ngoài mạng đã có version mới, vì cache của RUN không tự kiểm tra trạng thái repository. Hãy ghi nhận từng lớp riêng.

## 3. Tạo ứng dụng mẫu

Cấu trúc project:

§§§text
cache-lab/
├── pom.xml
├── build.gradle
├── settings.gradle
├── mvnw
├── .mvn/wrapper/
└── src/main/java/com/example/cachelab/
    ├── CacheLabApplication.java
    └── GreetingController.java
§§§

Dùng Maven hoặc Gradle cho một lượt thực hành, không cần duy trì cả hai build tool trong cùng pipeline.

### 3.1. Main class

File ¤src/main/java/com/example/cachelab/CacheLabApplication.java:

§§§java
package com.example.cachelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheLabApplication.class, args);
    }
}
§§§

### 3.2. Controller ban đầu

File ¤src/main/java/com/example/cachelab/GreetingController.java:

§§§java
package com.example.cachelab;

import java.util.Map;
import org.apache.commons.lang3.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/greeting")
    public Map<String, String> greeting(
            @RequestParam(defaultValue = "java") String name) {
        return Map.of("message", "Build A: " + StringUtils.capitalize(name));
    }
}
§§§

Controller dùng StringUtils.capitalize từ Apache Commons Lang để dependency xuất hiện trong runtime archive. Endpoint /greeting trả về JSON có field message.

### 3.3. Maven POM

File ¤pom.xml:

§§§xml
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
    <artifactId>cache-lab</artifactId>
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
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <finalName>cache-lab</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
§§§

finalName cố định executable archive thành target/cache-lab.jar. Nếu dự án có parent POM hoặc plugin configuration riêng, hợp nhất phần cần thiết thay vì thay thế toàn bộ cấu hình.

### 3.4. Gradle thay thế

File ¤build.gradle Groovy DSL:

§§§groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.apache.commons:commons-lang3:3.14.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootJar') {
    archiveFileName = 'cache-lab.jar'
}
§§§

File ¤settings.gradle:

§§§groovy
rootProject.name = 'cache-lab'
§§§

Ghi lại output ¤./gradlew --version trước khi bắt đầu; không nâng Gradle giữa các lượt đo.

## 4. Baseline: build lần đầu và build lại

Ghi nhận source và toolchain:

§§§bash
git rev-parse HEAD
git status --short
java -version
./mvnw -version
# Hoặc:
./gradlew --version
§§§

Nếu project chưa có Git commit, ghi lại snapshot source theo quy trình nhóm; không cần push.

### 4.1. Maven

Build lần đầu:

§§§bash
./mvnw --batch-mode clean package
test -s target/cache-lab.jar
jar tf target/cache-lab.jar
sha256sum target/cache-lab.jar
§§§

Trong JAR, tìm:

§§§text
BOOT-INF/classes/com/example/cachelab/CacheLabApplication.class
BOOT-INF/classes/com/example/cachelab/GreetingController.class
BOOT-INF/lib/commons-lang3-3.14.0.jar
BOOT-INF/lib/spring-boot-*.jar
§§§

Giữ nguyên source/POM rồi build lại:

§§§bash
./mvnw --batch-mode package
sha256sum target/cache-lab.jar
§§§

Ghi plugin/goal xuất hiện trong log, compiler có compile source hay bỏ qua, JAR có được ghi lại không và SHA-256 có giống lần đầu không. Maven không hiển thị task outcomes UP-TO-DATE/FROM-CACHE như Gradle; compiler/plugin có incremental behavior riêng. Không suy diễn từ việc build nhanh rằng Maven đã dùng task-output cache kiểu Gradle.

### 4.2. Gradle

Build lần đầu:

§§§bash
./gradlew clean bootJar --info
test -s build/libs/cache-lab.jar
jar tf build/libs/cache-lab.jar
sha256sum build/libs/cache-lab.jar
§§§

Build lại, không clean:

§§§bash
./gradlew bootJar --info
§§§

Đọc task outcomes:

- UP-TO-DATE: inputs/outputs không đổi trong workspace.
- FROM-CACHE: output được khôi phục từ local/remote build cache.
- NO-SOURCE: task không có source input cần xử lý.
- SKIPPED: task bị bỏ qua do điều kiện/command.
- Không có nhãn: task đã thực thi bình thường.

Để quan sát FROM-CACHE, chạy hai lần:

§§§bash
./gradlew clean bootJar --build-cache --info
./gradlew clean bootJar --build-cache --info
§§§

Nếu cache entry tồn tại và task đủ điều kiện cache, một số task có thể hiện FROM-CACHE. Nếu chạy bootJar lần hai mà không clean, task thường có thể là UP-TO-DATE thay vì FROM-CACHE, vì output vẫn nằm trong workspace. Không phải mọi task đều cacheable.

## 5. Thí nghiệm A: chỉ thay đổi một dòng Java

Mục tiêu: xem thay đổi source ảnh hưởng compile/package và image application layer thế nào trong khi dependency không đổi.

Trong GreetingController.java, đổi:

§§§java
return Map.of("message", "Build A: " + StringUtils.capitalize(name));
§§§

thành:

§§§java
return Map.of("message", "Build B: " + StringUtils.capitalize(name));
§§§

Không sửa POM/build.gradle và không đổi dependency version.

Build lại:

Maven:

§§§bash
./mvnw --batch-mode package
sha256sum target/cache-lab.jar
§§§

Gradle:

§§§bash
./gradlew bootJar --info
sha256sum build/libs/cache-lab.jar
§§§

Quan sát:

- GreetingController.java đã thay đổi nên class tương ứng phải được compile lại.
- Dependency không thay đổi nên không cần resolve version mới.
- Executable JAR thường có SHA-256 khác vì class bytes đã đổi.
- Các class/dependency không bị ảnh hưởng có thể được giữ nguyên; mức incremental cụ thể phụ thuộc compiler/build tool.

Chạy JAR mới:

§§§bash
java -jar target/cache-lab.jar
§§§

Ở terminal khác:

§§§bash
curl "http://localhost:8080/greeting?name=java"
§§§

Response mong đợi:

§§§json
{"message":"Build B: Java"}
§§§

Nếu vẫn thấy Build A, kiểm tra process có được khởi động từ JAR mới không. Process Java đang chạy không tự nạp lại JAR chỉ vì file trên đĩa được build lại. Dừng process cũ và khởi động process mới.

## 6. Thí nghiệm B: chỉ thay đổi dependency version

Mục tiêu: xem dependency resolution, runtime classpath và layer dependencies thay đổi thế nào khi Java source giữ nguyên.

### 6.1. Nâng Commons Lang

Trong Maven POM, đổi:

§§§xml
<version>3.14.0</version>
§§§

thành:

§§§xml
<version>3.15.0</version>
§§§

Trong Gradle, đổi:

§§§groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
§§§

thành:

§§§groovy
implementation 'org.apache.commons:commons-lang3:3.15.0'
§§§

Không sửa GreetingController.java trong thí nghiệm này.

### 6.2. Kiểm tra dependency thực sự được resolve

Maven:

§§§bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
./mvnw --batch-mode package
jar tf target/cache-lab.jar | grep commons-lang3
sha256sum target/cache-lab.jar
§§§

Gradle:

§§§bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew bootJar --info
jar tf build/libs/cache-lab.jar | grep commons-lang3
sha256sum build/libs/cache-lab.jar
§§§

Kết quả cần xác nhận là runtime archive chứa commons-lang3-3.15.0.jar. Không chỉ dựa vào giá trị trong POM/build.gradle: dependency management, constraints, resolution rules hoặc lockfile có thể làm version cuối cùng khác với declaration.

StringUtils.capitalize vẫn giữ cùng cách sử dụng. Việc nâng dependency nhằm quan sát classpath, archive và image layers; không khẳng định version mới làm thay đổi response.

### 6.3. Phân biệt dependency cache với task cache

- Maven local repository hoặc Gradle dependency cache lưu artifact đã tải và metadata resolve.
- Gradle FROM-CACHE là output của task được khôi phục từ build cache.
- Docker cache mount /root/.m2 hoặc Gradle User Home có thể giữ dependency downloads giữa các lần build container.
- Image layer chứa thư viện được đóng gói vào sản phẩm.

Một dependency version mới có thể cần tải file mới nhưng vẫn tái sử dụng dependency khác đã có trong local repository. Không cần xóa toàn bộ ~/.m2 hoặc ~/.gradle để thử thay một version.

## 7. Thí nghiệm C: quan sát Gradle task graph và build cache

Chỉ thực hiện phần này nếu project dùng Gradle.

Xem task graph:

§§§bash
./gradlew bootJar --dry-run
./gradlew tasks --all
./gradlew help --task bootJar
§§§

--dry-run hiển thị task sẽ được lên lịch nhưng không chạy actions. Dùng nó để xác nhận bootJar phụ thuộc các task compile/resources cần thiết.

Chạy hai lần liên tiếp:

§§§bash
./gradlew bootJar --info
./gradlew bootJar --info
§§§

Lần hai thường có nhiều task UP-TO-DATE nếu input/output không đổi. Sửa GreetingController.java rồi chạy lại; tìm compileJava và các task downstream đã chạy lại.

So sánh build cache:

§§§bash
./gradlew clean bootJar --build-cache --info
./gradlew clean bootJar --build-cache --info
./gradlew clean bootJar --no-build-cache --info
§§§

--no-build-cache tắt việc lấy task outputs từ Gradle build cache trong lượt chạy đó. Nó không tắt dependency cache và cũng không xóa Docker cache.

| Quan sát | Kết luận phù hợp |
| --- | --- |
| compileJava UP-TO-DATE khi source không đổi | Incremental check thấy inputs/outputs không đổi. |
| compileJava chạy sau khi sửa Java | Source input đã đổi và task cần thực thi. |
| Task FROM-CACHE sau clean | Output được phục hồi từ build cache, nếu task hỗ trợ cache. |
| Task SKIPPED | Kiểm tra onlyIf, enabled, -x hoặc điều kiện task. |
| Dependency insight cho thấy version mới | Dependency resolution đã chọn version mới. |
| JAR vẫn chứa version cũ | Kiểm tra module/artifact path, lockfile và bootJar; chưa thể kết luận cache là nguyên nhân. |

Không dùng --rerun-tasks như cách sửa lâu dài cho task khai báo thiếu input. Nếu custom task đọc file/property mà không khai báo input, cần sửa task model để Gradle tính đúng trạng thái.

## 8. Thí nghiệm D: quan sát Docker layer với Spring Boot layered JAR

Spring Boot có thể chia executable JAR thành các layer có tần suất thay đổi khác nhau. Layout mặc định thường gặp gồm:

1. dependencies: dependency release ít thay đổi.
2. spring-boot-loader: loader của Spring Boot.
3. snapshot-dependencies: dependency SNAPSHOT có thể thay đổi thường xuyên.
4. application: application classes và resources.

Kiểm tra layer index của archive thực tế thay vì giả định mọi dự án đều có layout giống nhau.

### 8.1. Dockerfile sử dụng Spring Boot tools jarmode

Sau khi build JAR vào target/cache-lab.jar (hoặc build/libs/cache-lab.jar nếu dùng Gradle), tạo file Dockerfile:

§§§dockerfile
FROM eclipse-temurin:17-jre AS extract
WORKDIR /layers

COPY target/cache-lab.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extract /layers/extracted/dependencies/ ./
COPY --from=extract /layers/extracted/spring-boot-loader/ ./
COPY --from=extract /layers/extracted/snapshot-dependencies/ ./
COPY --from=extract /layers/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
§§§

Nếu dùng Gradle, đổi source path ở dòng COPY đầu thành build/libs/cache-lab.jar. Archive cần có layer index và Spring Boot tools jarmode. Không dùng tools extraction với fully executable archive có launch script; hãy build archive phù hợp cho container layering.

Xem layer names:

§§§bash
java -Djarmode=tools -jar target/cache-lab.jar list-layers
§§§

Nếu command không có trong archive, kiểm tra Spring Boot version, plugin packaging và layer configuration. Không bỏ qua lỗi này bằng cách copy nhầm plain JAR.

### 8.2. Build image baseline

§§§bash
docker buildx build --load --progress=plain -t cache-lab:code-a .
docker buildx build --load --progress=plain -t cache-lab:code-a-repeat .
§§§

Ghi lại cache lines và instruction đã chạy. Tag khác không nhất thiết làm cache miss; Dockerfile cache phụ thuộc instruction và inputs, không chỉ tên tag.

### 8.3. Chỉ sửa Java code rồi build image lần nữa

Sau thí nghiệm A, JAR đã có response Build B. Build:

§§§bash
docker buildx build --load --progress=plain -t cache-lab:code-b .
§§§

Quan sát:

- COPY JAR vào stage extract có input mới.
- Lệnh java -Djarmode=tools ... extract chạy lại vì JAR input thay đổi.
- COPY layer dependencies có thể được cache nếu nội dung dependency không đổi.
- COPY spring-boot-loader có thể được cache nếu loader không đổi.
- COPY snapshot-dependencies có thể được cache nếu không có snapshot dependency thay đổi.
- COPY application cần cập nhật vì application code/resource đã đổi.

Đây là kết quả kỳ vọng của layered JAR khi chỉ sửa application code. Log builder là bằng chứng cuối cùng; timestamp, metadata hoặc cấu hình layer tùy chỉnh có thể ảnh hưởng cache key.

### 8.4. Chỉ nâng dependency version rồi build image

Đưa dependency từ 3.14.0 lên 3.15.0 như thí nghiệm B, build JAR mới rồi chạy:

§§§bash
docker buildx build --load --progress=plain -t cache-lab:dependency-b .
§§§

Kỳ vọng: stage extract chạy lại; layer dependencies thay đổi; layer application có thể được giữ lại nếu app classes/resources không đổi; layer loader thường không đổi nếu Spring Boot version không đổi; layer snapshot-dependencies chỉ đổi khi snapshot dependency liên quan thay đổi.

Nếu nhiều layer thay đổi, kiểm tra layer contents và build metadata trước khi kết luận Docker cache hoạt động sai.

### 8.5. So sánh image ID và filesystem layer digests

§§§bash
docker image inspect --format '{{.Id}}' cache-lab:code-a
docker image inspect --format '{{.Id}}' cache-lab:code-b
docker image inspect --format '{{json .RootFS.Layers}}' cache-lab:code-a
docker image inspect --format '{{json .RootFS.Layers}}' cache-lab:code-b
docker history --no-trunc cache-lab:code-a
docker history --no-trunc cache-lab:code-b
§§§

Cần phân biệt image config ID, RootFS layer diff IDs và registry manifest digest. Chúng là các digest khác nhau. docker history cho biết lịch sử/layer metadata và kích thước hiển thị, nhưng không thay thế việc so sánh từng filesystem layer. Image local chưa push có thể chưa có RepoDigest.

### 8.6. Kiểm tra image chạy đúng code mới

§§§bash
docker run --rm -p 8080:8080 cache-lab:code-b
§§§

Ở terminal khác:

§§§bash
curl "http://localhost:8080/greeting?name=java"
§§§

Response mong đợi là Build B. Container cũ vẫn dùng image ID đã gắn khi container được tạo. Recreate container sau khi xác nhận tag mới trỏ tới image mong muốn.

## 9. Thí nghiệm E: BuildKit cache mount cho Maven dependency

Docker layer cache và dependency cache có thể hoạt động cùng lúc. BuildKit cache mount giữ dữ liệu Maven trong builder cache, nhưng nội dung mount không được đóng vào image layer.

Dockerfile nhiều stage:

§§§dockerfile
# syntax=docker/dockerfile:1

FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY mvnw pom.xml ./
COPY .mvn ./.mvn
RUN chmod +x mvnw

RUN --mount=type=cache,target=/root/.m2 ./mvnw -B dependency:go-offline

COPY src ./src
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B package -DskipTests

FROM eclipse-temurin:17-jre AS extract
WORKDIR /layers
COPY --from=build /workspace/target/cache-lab.jar application.jar
RUN java -Djarmode=tools -jar application.jar extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application
COPY --from=extract /layers/extracted/dependencies/ ./
COPY --from=extract /layers/extracted/spring-boot-loader/ ./
COPY --from=extract /layers/extracted/snapshot-dependencies/ ./
COPY --from=extract /layers/extracted/application/ ./
ENTRYPOINT ["java", "-jar", "application.jar"]
§§§

Ví dụ giả định project có Maven Wrapper và thư mục .mvn/. CI cần chạy tests trước bước image build; -DskipTests ở đây chỉ rút gọn bước package. Nếu muốn test trong build stage, bỏ cờ này và cấu hình pipeline phù hợp.

Tạo .dockerignore cho build-in-container:

§§§text
.git
.idea
.gradle
build/
target/
**/.env
**/.env.*
**/secrets/**
**/*.pem
**/*.key
**/*.p12
**/*.jks
§§§

Trong Dockerfile này JAR được tạo bên trong stage build, nên loại target/ khỏi context là hợp lý.

### 9.1. Chạy build và thay đổi source

§§§bash
docker buildx build --load --progress=plain -t cache-lab:inside-a .
docker buildx build --load --progress=plain -t cache-lab:inside-a-repeat .
§§§

Khi không đổi input, COPY POM/wrapper và dependency:go-offline có thể cache hit; cache mount /root/.m2 giữ dependency artifacts; COPY src và package có thể cache hit nếu source không đổi.

Đổi Build A thành Build B rồi build lại. COPY src đổi nên instruction downstream trong stage build phải thực thi lại; dependency resolution phía trước có thể vẫn cache hit. Cache mount /root/.m2 vẫn có thể cung cấp dependency đã tải.

### 9.2. Đổi dependency version trong POM

Khi đổi Commons Lang 3.14.0 thành 3.15.0, COPY pom.xml đổi và làm mất cache cho instruction phía sau trong stage build; dependency:go-offline chạy lại; cache mount /root/.m2 vẫn có thể giữ dependency cũ và tải thêm version cần thiết; package chạy với dependency graph mới.

Không đưa password/token vào build ARG để bust cache. BuildKit không đưa secret value vào cache checksum; nếu cần invalidation theo cấu hình không bí mật, dùng version marker không chứa secret và chỉ khi output thực sự phụ thuộc marker đó.

## 10. Thí nghiệm F: Cloud Native Buildpacks (CNB)

Spring Boot Maven/Gradle plugin có thể tạo image từ executable archive bằng CNB. Buildpacks dùng layers và có thể restore/reuse cache theo metadata.

Build cùng một image name:

§§§bash
./mvnw spring-boot:build-image -Dspring-boot.build-image.imageName=cache-lab:cnb
./mvnw spring-boot:build-image -Dspring-boot.build-image.imageName=cache-lab:cnb
§§§

Tìm trong builder logs thông tin analyze, restore, build, export và layer reuse. Không giả định mọi buildpack hiển thị cùng một câu log; đọc thông báo của builder/version đang dùng.

Sửa Java source rồi chạy lại cùng image name. Theo dõi layer nào được restore/rebuild. Application layer thường có thay đổi; dependency/JRE layers có thể được reuse nếu metadata/input tương ứng không đổi.

Nâng Commons Lang version rồi build lại image với cùng target image name. Quan sát dependency layer. Nếu đổi tag/image name ở mỗi lượt, tên cache volume mặc định của Spring Boot plugin có thể đổi theo full target image name và làm giảm khả năng reuse.

So sánh với cache đã làm sạch:

§§§bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=cache-lab:cnb \
  -Dspring-boot.build-image.cleanCache=true
§§§

cleanCache yêu cầu làm sạch cache buildpack cho lần build đó. Nó không xóa Maven local repository, Gradle dependency cache, Docker BuildKit cache hoặc runtime cache. Không xóa mọi Docker volumes để ép CNB build lại; chỉ quản lý cache volume đúng project/owner.

Kiểm tra image:

§§§bash
docker image inspect --format '{{.Id}}' cache-lab:cnb
docker history --no-trunc cache-lab:cnb
§§§

Nếu có pack CLI, dùng pack inspect-image cache-lab:cnb để xem metadata/layers theo thông tin CNB. Cấu trúc layer cụ thể phụ thuộc builder/buildpacks và version; ghi lại builder image và buildpack versions cùng kết quả.

## 11. Bảng dự đoán và bằng chứng cần ghi

| Lượt | Thay đổi | Maven/Gradle | JAR | Docker/CNB image |
| --- | --- | --- | --- | --- |
| 0 | Build baseline | Build đầy đủ; Gradle lần đầu thường thực thi tasks. | Lưu SHA-256 ban đầu. | Lưu image ID và layer diff IDs. |
| 1 | Build lại không đổi input | Gradle có thể UP-TO-DATE; Maven/plugin có thể bỏ một số thao tác. | Thường cùng nội dung nếu không có timestamp động. | Nhiều instruction/layer có thể cache hit/reuse. |
| 2 | Chỉ sửa Java source | Compile task liên quan chạy lại; dependency resolution không cần đổi version. | SHA-256 thường đổi. | Layer application thường đổi; dependency layers có thể reuse. |
| 3 | Chỉ đổi dependency version | Resolve dependency mới; compile/package dùng classpath mới. | SHA-256 đổi và nested JAR version đổi. | Dependency layer đổi; application layer có thể giữ nếu app source không đổi. |
| 4 | Cache bị vô hiệu có chủ đích | Task/lệnh cần chạy lại; dependency downloads vẫn có thể tồn tại ở cache riêng. | So digest với lượt tương ứng. | Nhiều instruction/layer được tạo lại; không mặc định bytes khác. |

Ghi commit SHA, Java/wrapper versions, dependency version trước/sau, build command, task outcome hoặc Docker cache lines, JAR filename/size/SHA-256, image tag/config ID/RootFS layer diff IDs, response endpoint và builder/buildpack versions nếu dùng CNB.

Không điền PASS chỉ vì command exit code 0. Cần xác nhận artifact, dependency và runtime response thực sự phản ánh thay đổi.

## 12. Cách diễn giải các trường hợp thường gặp

### Java source đã đổi nhưng JAR không đổi

Kiểm tra đúng source file/module, Maven package hoặc Gradle bootJar có chạy không, đang hash đúng artifact hay plain JAR, có copy artifact từ thư mục khác đè lên output không và archive contents có phản ánh bytecode mới không.

Nếu Gradle báo UP-TO-DATE dù source đã đổi, kiểm tra source set, task inputs và file path. Nếu Docker image cũ nhưng JAR mới, kiểm tra Docker build context và COPY source path.

### Dependency version đổi nhưng JAR vẫn chứa version cũ

Kiểm tra dependency graph:

§§§bash
./mvnw dependency:tree -Dincludes=org.apache.commons:commons-lang3
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
§§§

Kiểm tra lockfile, constraints, BOM, dependencyManagement và đúng module. Build lại đúng Boot archive, kiểm tra BOOT-INF/lib/. Nếu version mới chưa resolve được, kiểm tra repository/mirror và lỗi download; không xóa toàn bộ dependency cache để che nguyên nhân.

### Docker build báo cache hit dù package repository đã có version mới

Docker cache của RUN dựa trên instruction và layer trước, không kiểm tra nội dung repository ngoài mạng. Pin package version hoặc chủ động invalidation stage cần thiết. --pull cập nhật base image; --no-cache buộc thực thi lại Dockerfile instructions trong lượt build đó. Hai tùy chọn giải quyết mục tiêu khác nhau.

### Docker application layer thay đổi dù chỉ đổi dependency

Kiểm tra layer index và extracted contents. Một số cấu hình có thể đưa generated metadata hoặc dependency metadata vào application layer. So sánh directory contents/digests trước khi kết luận cache sai. Layer names cho biết ranh giới đóng gói, không phải cam kết mọi dự án luôn có cùng diff IDs.

### CNB không reuse cache giữa hai lượt

Kiểm tra target image name có thay đổi không. Spring Boot plugin mặc định đặt tên build/launch cache volumes dựa trên full image name. Dùng cùng image name để thí nghiệm reuse; ghi builder/buildpack version và logs restore/analyze.

### Image tag đã đổi nhưng container trả response cũ

Tag là reference có thể di chuyển; container đã tạo vẫn giữ image ID lúc khởi chạy. Kiểm tra:

§§§bash
docker image inspect --format '{{.Id}}' cache-lab:code-b
docker inspect --format '{{.Image}}' <CONTAINER_ID>
§§§

Nếu ID khác nhau, recreate container/service theo quy trình deploy. Không cần xóa build cache để xử lý container cũ.

## 13. Các lỗi thực hành và cách sửa

| Lỗi | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Đổi tag mỗi lần rồi kết luận CNB cache không hoạt động. | Cache volume mặc định có thể phụ thuộc full image name. | Giữ target image name ổn định trong thí nghiệm. |
| Dùng clean trước mọi lượt rồi mong thấy UP-TO-DATE. | clean xóa project outputs. | Chạy một lượt không clean để quan sát incremental state. |
| Nhầm Gradle FROM-CACHE với dependency cache. | Hai cache lưu loại dữ liệu khác nhau. | Đọc task outcome và dependencyInsight riêng. |
| Maven không hiện task outcome giống Gradle. | Maven lifecycle/plugin log không dùng cùng task model. | Đọc phase/goal và compiler/plugin logs. |
| Đổi mtime file để mong Docker COPY cache miss. | Docker không dùng mtime riêng làm cache checksum. | Thay đổi nội dung input thật. |
| RUN apt update vẫn cache hit. | Cache lookup không kiểm tra trạng thái mạng. | Pin inputs và dùng --no-cache-filter/--no-cache có chủ đích. |
| Secret đổi nhưng RUN vẫn cache hit. | Secret value không tham gia cache checksum. | Thiết kế output không phụ thuộc secret; dùng non-secret version marker nếu cần. |
| Dependency mới không xuất hiện trong image. | Image build dùng JAR cũ hoặc Dockerfile COPY nhầm path. | Xác nhận JAR trước, rồi kiểm tra archive path. |
| Image layer nào cũng đổi sau sửa một dòng. | Copy nguyên uber JAR vào một layer hoặc metadata/layer layout thay đổi. | Dùng layered JAR và so extracted directories. |
| Docker build không tìm thấy JAR. | .dockerignore loại target/build hoặc path sai. | Kiểm tra context và đường dẫn archive. |
| Tools jarmode không chạy. | Layer index/tools mode không được đóng vào archive hoặc archive có launch script. | Kiểm tra Boot plugin packaging và list-layers. |
| Container chạy code cũ. | Container đang dùng image ID cũ. | Recreate container từ image mới. |
| Build image CNB không có Docker daemon. | Plugin cần kết nối Docker daemon/context. | Kiểm tra Docker context/daemon và quyền truy cập. |
| Clean toàn bộ cache làm mất dữ liệu project khác. | Cache dùng chung giữa project/runner. | Xóa theo owner, volume và lifecycle cụ thể. |

## 14. Làm sạch và khôi phục sau thí nghiệm

Giữ lại JAR, SHA-256, Docker build logs/layer digests, CNB builder logs/image metadata, dependency tree trước/sau và source diff trước khi dọn.

| Lệnh | Phạm vi |
| --- | --- |
| ./mvnw clean | Xóa generated outputs Maven trong project theo clean configuration. |
| ./gradlew clean | Xóa project build outputs, thường là build/. |
| ./gradlew --no-build-cache | Tắt lấy task output từ Gradle build cache cho build đó. |
| ./gradlew --refresh-dependencies | Làm mới dependency resolution state. |
| docker build --no-cache | Bỏ Dockerfile layer cache cho lượt build. |
| docker build --pull | Yêu cầu cập nhật base images theo pull policy. |
| -Dspring-boot.build-image.cleanCache=true | Yêu cầu Spring Boot Maven plugin làm sạch CNB cache cho image build đó. |

Không dùng docker system prune -a --volumes, xóa toàn bộ ~/.m2, ~/.gradle hoặc remote cache dùng chung chỉ để hoàn tất lab. Nếu cần xóa image/container do chính bạn tạo, xác nhận tên cụ thể:

§§§bash
docker image ls cache-lab
docker ps -a --filter ancestor=cache-lab:code-b
§§§

Dừng/xóa đúng container thử nghiệm và image do lab tạo theo policy máy. Không xóa builder/cache volume đang được project hoặc job khác sử dụng.

## 15. Bài mở rộng

### So sánh uber JAR với layered JAR

Tạo Dockerfile chỉ copy toàn bộ cache-lab.jar vào một layer. Build baseline rồi sửa một dòng Java. So sánh với Dockerfile dùng jarmode=tools extract --layers. Phân tích số layer, kích thước layer thay đổi và cache reuse ở từng COPY.

Không khẳng định layered image luôn nhỏ hơn về tổng bytes; lợi ích chính trong lab là cache/pull theo phần thay đổi.

### Thử snapshot dependency và base image

Trong môi trường Maven/Gradle riêng, tạo một module SNAPSHOT hoặc dependency changing để quan sát khác biệt với release dependency cố định. Ghi repository update policy và dependency cache. Sau đó build hai image với cùng JAR nhưng base image tag/digest khác; so sánh trường hợp application layer không đổi nhưng image digest thay đổi.

### Kiểm tra reproducibility

Build hai workspace độc lập từ cùng commit, cùng wrapper/JDK/dependency versions và cùng base image digest. So SHA-256 của JAR, sau đó so layer diff IDs. Nếu JAR giống nhưng image khác, kiểm tra builder/run image, created date, architecture và metadata. Nếu JAR khác, dùng diffoscope hoặc extract archive để tìm timestamp, file ordering và generated metadata.

## 16. Checklist hoàn thành

### Build tool

- [ ] Đã ghi commit, JDK và wrapper versions.
- [ ] Đã build baseline từ Maven hoặc Gradle.
- [ ] Đã build lại không thay đổi input và đọc đúng log.
- [ ] Đã sửa một dòng Java, build lại và kiểm tra response mới.
- [ ] Đã nâng Commons Lang version, kiểm tra dependency graph và nested JAR.
- [ ] Đã phân biệt Gradle UP-TO-DATE, FROM-CACHE, SKIPPED, NO-SOURCE.
- [ ] Không nhầm Maven compiler/plugin behavior với Gradle task outcomes.

### Docker/CNB

- [ ] Đã build Docker image từ layered Spring Boot JAR.
- [ ] Đã đọc cache lines trong BuildKit log.
- [ ] Đã so sánh image config ID và RootFS layer diff IDs.
- [ ] Đã quan sát application-only change.
- [ ] Đã quan sát dependency-only change.
- [ ] Đã xác minh container chạy image mới.
- [ ] Đã thử CNB với image name ổn định và đọc layer restore/rebuild logs.
- [ ] Đã phân biệt Docker layer cache, BuildKit cache mount và CNB build/launch cache.

### Kết luận và bằng chứng

- [ ] Có SHA-256 cho từng JAR được tạo.
- [ ] Có dependency version trước/sau.
- [ ] Có log task outcome hoặc Docker cache outcome.
- [ ] Có image IDs/layer digests trước/sau.
- [ ] Có response endpoint trước/sau.
- [ ] Không xóa cache dùng chung hoặc artifact ngoài phạm vi lab.
- [ ] Không tuyên bố một layer đã reuse nếu log/digest không chứng minh điều đó.

**Tiêu chí đạt:** người học thay đổi được code và dependency ở hai lượt riêng biệt; chứng minh JAR/runtime dependency đã thay đổi; giải thích task/cache behavior của Maven hoặc Gradle; chỉ ra Docker/CNB layer nào được cache hoặc rebuild bằng logs và image metadata; và xác minh container trả về response từ image mới. Nếu Docker daemon/CNB builder không khả dụng, ghi rõ phần chưa chạy và không đánh dấu image-layer experiment là hoàn tất chỉ từ việc build JAR.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.3 — Efficient Deployments](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.3 — Dockerfiles and Layered Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3.13 — Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 — Gradle Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Docker — Build Cache](https://docs.docker.com/build/cache/)
- [Docker — Cache Invalidation](https://docs.docker.com/build/cache/invalidation/)
- [Docker — Cache Optimization](https://docs.docker.com/build/cache/optimize/)
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Build Cache Debugging](https://docs.gradle.org/current/userguide/build_cache_debugging.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)

**Ghi nhớ:** sửa code chủ yếu tác động application inputs/layer; đổi dependency tác động dependency resolution, executable archive và dependency layer; đổi base image tác động nền image. Hãy giữ mỗi thí nghiệm chỉ thay một yếu tố, đọc log cache, so SHA-256/layer digests và kiểm tra response từ container mới. Cache chỉ là tối ưu hóa; bằng chứng phải cho thấy đúng output đã được tạo và đúng image đang chạy.