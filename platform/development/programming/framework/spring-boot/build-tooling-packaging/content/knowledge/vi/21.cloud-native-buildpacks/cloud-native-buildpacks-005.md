# Phân biệt build-image với build-image-no-fork khi gắn vào Maven lifecycle

## 1. Mục tiêu và tình huống thực tế

Spring Boot Maven Plugin cung cấp hai goal gần giống tên:

- `spring-boot:build-image`.
- `spring-boot:build-image-no-fork`.

Cả hai dùng **Cloud Native Buildpacks (CNB)** để tạo **OCI container image** từ ứng dụng Spring Boot mà không cần viết Dockerfile. Khác biệt cốt lõi không nằm ở format image hay phiên bản Java, mà ở **cách Maven thực thi build lifecycle trước khi tạo image**:

- **`build-image` fork Maven lifecycle đến `package`** để chuẩn bị artifact. Đây là goal Spring Boot khuyên dùng khi **gọi trực tiếp bằng lệnh CLI**.
- **`build-image-no-fork` không fork lifecycle**. Đây là goal Spring Boot khuyên dùng **trong một plugin execution** đã được Maven gắn với phase như `package`, tránh yêu cầu package lần thứ hai.

Chọn nhầm goal khi bind vào POM có thể khiến Maven chạy lại compile/test/package và các plugin executions không cần thiết. Gọi no-fork trực tiếp từ source chưa build cũng có thể khiến artifact thiếu hoặc cũ.

Sau bài này, bạn có thể:

1. Giải thích Maven phase, plugin goal, execution và lifecycle fork.
2. Tạo OCI image bằng CLI `./mvnw spring-boot:build-image` mà không cần tự gọi `package` trước.
3. Gắn `build-image-no-fork` vào `package` trong Maven profile `container` để tạo image có chủ đích.
4. Viết một ứng dụng Java 17/Spring MVC, POM đầy đủ và test có thể chạy.
5. Phân biệt `repackage`, JAR/WAR, CNB builder, Docker daemon, local image và registry publication.
6. Kiểm tra đúng image bằng `docker image inspect` và container smoke test.
7. Hiểu vì sao image gắn `package` có thể được tạo **trước các integration tests ở `verify`** và lựa chọn release gate phù hợp.
8. Xử lý các lỗi build-image trùng, Docker daemon, Maven multi-module, profile, image tag và Java runtime.

**Phiên bản mẫu: Spring Boot 3.3.5**, Java 17, Spring Boot Starter Parent và Maven Wrapper được cấu hình phù hợp. Đây là phiên bản minh họa các API/config cụ thể, không phải bản mới nhất cần sử dụng cho mọi dự án. Hãy đối chiếu tài liệu Spring Boot Maven Plugin theo phiên bản dự án thực tế.

## 2. Cloud Native Buildpacks tạo image như thế nào?

Cloud Native Buildpacks có **builder image**, bộ buildpacks và lifecycle thực hiện detect/build/export. Builder đọc application archive, lựa chọn runtime (ví dụ Java), tạo các layers và launch process, rồi tạo OCI image dựa trên một run image thích hợp.

~~~text
Java source + pom.xml
        |
        v
Maven compile / test / package
        |
        v
JAR hoặc WAR của ứng dụng
        |
        v
Spring Boot Maven Plugin image goal
        |
        v
CNB builder + buildpacks + lifecycle
        |
        v
OCI image (filesystem layers + launch metadata)
        |
        v
Docker daemon hoặc container registry
        |
        v
Container chạy ứng dụng
~~~

**Không dùng Dockerfile:** hai goal của Spring Boot plugin trong bài này không thực thi `docker build .`. Một Dockerfile có sẵn trong repository không tự được CNB plugin đọc và chạy. Nếu bạn cần kiểm soát chính xác các lệnh `RUN`/`COPY` hoặc lựa chọn base image kiểu Dockerfile, hãy dùng Dockerfile workflow riêng.

**Vẫn cần Docker daemon:** Spring Boot Maven Plugin 3.3 kết nối Docker daemon để tạo image. Maven compile/test có thể hoạt động dù Docker Desktop/Engine chưa chạy, nhưng goal build-image có thể fail. Builder/run images và dependencies có thể cần network, registry credentials hoặc mirror nội bộ.

| Thành phần | Vai trò chính |
| --- | --- |
| Maven lifecycle | Biên dịch, chạy test, đóng gói ứng dụng |
| `spring-boot:repackage` | Tạo Spring Boot executable JAR/WAR với loader và nested dependencies |
| `spring-boot:build-image` | Fork lifecycle package rồi đưa ứng dụng vào CNB image build |
| `spring-boot:build-image-no-fork` | Đưa ứng dụng vào CNB image build mà không fork lifecycle |
| CNB builder image | Môi trường xây image, phát hiện Java và chạy buildpacks |
| CNB run image | Thành phần nền của container image lúc chạy |
| Docker daemon | Nơi plugin giao tiếp để tạo/lưu image |
| OCI registry | Nơi image được publish khi đã được cấu hình, không đồng nghĩa Docker daemon local |

## 3. Maven lifecycle: phase và goal là hai khái niệm khác nhau

Những phase chính của Maven default lifecycle:

~~~text
validate
    |
    v
compile
    |
    v
test
    |
    v
package
    |
    v
verify
    |
    v
install
    |
    v
deploy
~~~

Maven còn có các pha trung gian như `process-resources`, `test-compile`, `prepare-package` và `integration-test`. Khi chạy:

~~~bash
./mvnw clean package
~~~

Maven làm sạch build output rồi chạy các pha default lifecycle **đến package**. Điều đó thường bao gồm compiler, Surefire unit tests và tạo archive theo packaging/plugin configuration.

Khi chạy:

~~~bash
./mvnw clean verify
~~~

Maven còn thực thi các pha sau package đến `verify`. Những kiểm thử tích hợp dùng Maven Failsafe có thể chạy trong `integration-test` và được xác nhận ở `verify`.

**Khác nhau cần nhớ:**

- `package`: tên một **phase** trong lifecycle, không phải Spring Boot goal.
- `spring-boot:build-image`: tên **goal** có thể gọi từ CLI.
- `<execution>`: ràng buộc một hoặc nhiều plugin goals với phase.
- **Forked lifecycle**: một goal yêu cầu Maven chạy thêm các pha để chuẩn bị dữ liệu; không liên quan Git fork hay Docker process fork.

Vì vậy, lệnh `./mvnw package` không tương đương với `./mvnw spring-boot:build-image`.

## 4. build-image: có fork package, phù hợp gọi từ CLI

Theo Spring Boot Maven Plugin 3.3, goal `build-image` **fork Maven package lifecycle** để bảo đảm artifact đã được đóng gói trước khi buildpacks tạo OCI image.

~~~bash
./mvnw spring-boot:build-image
~~~

Sơ đồ:

~~~text
CLI: mvnw spring-boot:build-image
                |
                v
Maven thực thi goal build-image
                |
                v
FORK package lifecycle
(compile -> test -> package và các executions liên quan)
                |
                v
JAR/WAR sẵn sàng
                |
                v
CNB detect / build / export image
~~~

**Ưu điểm:** developer không cần nhớ phải gọi riêng `./mvnw package` trước đó. Một lệnh CLI có thể chuẩn bị archive rồi tạo image.

Nếu muốn build từ workspace sạch:

~~~bash
./mvnw clean spring-boot:build-image
~~~

Trong PowerShell:

~~~powershell
.\mvnw.cmd clean spring-boot:build-image
~~~

**Tránh tổ hợp sau nếu không có lý do cụ thể:**

~~~bash
./mvnw package spring-boot:build-image
~~~

Phần package được gọi tường minh và mục tiêu build-image có thể **fork package lại**, dẫn tới compile/tests/plugin executions chạy thêm. Điều đó không có nghĩa Maven luôn lỗi hoặc lặp vô tận, nhưng tạo công việc dư thừa và làm CI khó dự đoán.

**Tình huống phù hợp:** một lệnh build image chủ động trên máy developer, hoặc một CI job chuyên tạo image sau khi hệ thống đã quyết định bắt đầu công đoạn image packaging.

## 5. build-image-no-fork: không fork package, dành cho execution

Goal `build-image-no-fork` tạo OCI image bằng cùng cơ chế CNB nhưng **không tự chạy package lifecycle trước đó**. Nó được thiết kế để hoạt động khi một **lifecycle đang diễn ra** đã đưa Maven tới pha phù hợp, ví dụ `package`.

~~~xml
<execution>
    <id>make-image-on-package</id>
    <phase>package</phase>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

Trong Spring Boot 3.3, goal này có default phase `package`; ghi rõ `<phase>package</phase>` giúp người đọc không phải ghi nhớ mặc định.

~~~text
CLI: mvnw -Pcontainer clean package
                |
                v
Maven chạy lifecycle đến package
                |
                v
Compiler -> tests -> JAR/WAR
                |
                v
Execution: build-image-no-fork
                |
                v
CNB tạo OCI image
(không gọi lại package lifecycle)
~~~

**Không hiểu no-fork là bỏ qua compilation/testing.** Các pha trước package vẫn chạy bình thường do Maven lifecycle bên ngoài. No-fork chỉ tránh tạo ra một lượt lifecycle package phụ từ chính goal tạo image.

### Bảng so sánh chính

| Câu hỏi | `build-image` | `build-image-no-fork` |
| --- | --- | --- |
| Có tạo OCI image bằng buildpacks? | Có | Có |
| Có fork package lifecycle trước goal? | **Có** | **Không** |
| Dùng ở đâu? | CLI độc lập | Maven `<executions>` gắn phase |
| Lệnh mẫu | `./mvnw spring-boot:build-image` | `./mvnw -Pcontainer package` với POM binding |
| Nếu chưa package? | Tự yêu cầu package lifecycle | Không bảo đảm package đã chạy |
| Có cần Docker daemon? | Có | Có |
| Có cần Dockerfile? | Không | Không |
| Có mặc định push registry? | Không | Không |
| Có đảm bảo integration tests ở verify đã pass? | Không; fork đến package | Không nếu execution ở package |
| Có thể repackage executable archive khi cần? | Có | Có |
| Có phù hợp bind vào package? | **Không khuyến nghị** | **Đúng use case** |

**Quy tắc ngắn gọn:** **Gọi CLI → `build-image`. Gắn goal vào lifecycle → `build-image-no-fork`.**

## 6. Phân biệt repackage với image creation

Spring Boot Maven Plugin goal `repackage` có nhiệm vụ biến archive Maven thành Spring Boot **executable JAR/WAR**. JAR thường có:

~~~text
target/cnb-maven-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/...
    └── lib/...
~~~

Trong khi đó, `build-image`/`build-image-no-fork` sử dụng buildpacks để tạo **OCI image** có Java runtime, layers và launch configuration.

Theo tài liệu Spring Boot 3.3, **không nhất thiết phải tự gọi `spring-boot:repackage` riêng trước image goal**: nếu archive executable cần thiết chưa được tạo, image goal có thể repackage tự động theo cấu hình plugin. Các tùy chọn exclude dependencies của repackage cũng có ý nghĩa khi image goal tạo/repackage ứng dụng.

Tuy nhiên:

- `build-image-no-fork` **không tự chạy Maven compiler/package** nếu được gọi riêng khi chưa có artifact.
- Với `spring-boot-starter-parent`, repackage execution tiêu chuẩn thường đã được quản lý và kích hoạt khi plugin được khai báo.
- Với corporate parent chỉ import Spring Boot BOM, cần cấu hình đúng plugin version và executions; import BOM không tự tạo đầy đủ plugin bindings.
- Không khai báo hai repackage executions trùng khi parent đã có một execution phù hợp.
- Nếu module là Java library không có main class, không mặc định nó sẽ tạo được container image runnable như Spring Boot application.

## 7. Ví dụ Spring Boot Java 17 đầy đủ

Dự án ví dụ `cnb-maven-demo`:

~~~text
cnb-maven-demo/
├── pom.xml
├── mvnw, mvnw.cmd, .mvn/wrapper/...
└── src/
    ├── main/java/com/example/cnb/
    │   ├── CnbMavenDemoApplication.java
    │   └── PingController.java
    └── test/java/com/example/cnb/
        └── PingControllerTest.java
~~~

Dự án giả định Maven Wrapper thực sự được tạo và commit. Không thể chỉ đặt tên file `mvnw` mà thiếu wrapper implementation rồi kỳ vọng chạy.

### 7.1. File CnbMavenDemoApplication.java

Đường dẫn `src/main/java/com/example/cnb/CnbMavenDemoApplication.java`:

~~~java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CnbMavenDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CnbMavenDemoApplication.class, args);
    }
}
~~~

Đây là public main class hợp lệ. Dùng `spring-boot-starter-web`, Spring MVC và embedded Tomcat sẽ được cấu hình; không chạy source bằng `javac` độc lập nếu chưa có Spring Boot dependencies trên classpath.

### 7.2. File PingController.java

Đường dẫn `src/main/java/com/example/cnb/PingController.java`:

~~~java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`PingController` nằm trong package được `@SpringBootApplication` component scan. Khi Spring Boot đã startup, `GET /ping` trả response body:

~~~text
pong
~~~

Các dòng startup log chứa thời gian, PID/port thay đổi; không coi toàn bộ startup stdout là một chuỗi cố định.

### 7.3. File PingControllerTest.java

Đường dẫn `src/test/java/com/example/cnb/PingControllerTest.java`:

~~~java
package com.example.cnb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PingController.class)
class PingControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

Test này xác minh Spring MVC mapping bằng `@WebMvcTest`; **không chạy Docker**, không kiểm tra buildpacks và không bảo đảm image thật khởi động được. Để chứng minh image runnable cần thêm smoke test.

## 8. POM hoàn chỉnh cho cách gọi build-image trực tiếp

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cnb-maven-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
                        <name>docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT</name>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM đầy đủ cho project mẫu.**

- Spring Boot Starter Parent quản lý dependency/plugin versions và cấu hình build phù hợp.
- `<packaging>jar</packaging>` và Spring Boot Maven Plugin phục vụ executable JAR.
- `java.version=17` đồng bộ Java source/target cho ví dụ.
- `spring-boot-starter-web` cung cấp Spring MVC/runtime; `spring-boot-starter-test` chỉ phục vụ test.
- `<image><name>...` chỉ rõ image tag, tránh phụ thuộc implicit name trong các lệnh `docker run`.
- Chưa có `build-image-no-fork` execution: `./mvnw package` **không tự tạo OCI image** chỉ vì Spring Boot Maven Plugin đã được khai báo.

Đừng ghi đè POM thật của hệ thống đang dùng corporate parent; chuyển các nội dung liên quan vào đúng plugin/profile với version và naming convention đã có.

## 9. Thử lệnh CLI build-image

### 9.1. Kiểm tra môi trường

Linux/macOS:

~~~bash
java -version
./mvnw --version
docker version
docker info
~~~

Windows PowerShell:

~~~powershell
java -version
.\mvnw.cmd --version
docker version
docker info
~~~

Maven Wrapper cần dùng đúng JDK phù hợp. Docker CLI có thể tồn tại nhưng daemon không kết nối được; trong trường hợp đó compile/test vẫn có thể pass còn goal build-image fail.

### 9.2. Tạo image bằng goal riêng

Linux/macOS:

~~~bash
./mvnw spring-boot:build-image
~~~

PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:build-image
~~~

Goal sẽ đảm bảo `package` được chạy thông qua fork lifecycle. Khi cần build sạch:

~~~bash
./mvnw clean spring-boot:build-image
~~~

Log có thể chứa Maven compiler/Surefire/JAR/repackage và các bước CNB detect/build/export. Không ấn định chính xác stdout hoặc thời gian, vì cache, builder và network khác nhau.

### 9.3. Kiểm tra JAR và OCI image

Linux/macOS:

~~~bash
jar tf target/cnb-maven-demo-0.0.1-SNAPSHOT.jar |
    grep '^BOOT-INF/'
docker image inspect docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

Windows PowerShell:

~~~powershell
jar tf .\target\cnb-maven-demo-0.0.1-SNAPSHOT.jar |
    Select-String '^BOOT-INF/'
docker image inspect docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

Nếu `docker image inspect` trả metadata, image có trong Docker daemon/context đang kết nối; điều đó **không chứng minh** image đã publish lên một registry. Không đoán image digest từ tên tag.

### 9.4. Chạy smoke test trên container

Terminal thứ nhất:

~~~bash
docker run --rm -p 8080:8080 docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

Terminal thứ hai:

~~~bash
curl -fsS http://localhost:8080/ping
~~~

Expected HTTP response body:

~~~text
pong
~~~

Trên PowerShell:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/ping"
~~~

Nếu host port 8080 đã được sử dụng, chạy `docker run --rm -p 8081:8080 ...` rồi gọi `http://localhost:8081/ping`. Không map hai container cùng host port trong cùng thời điểm.

## 10. Gắn build-image-no-fork vào Maven lifecycle bằng profile

Để developer/CI chỉ tạo OCI image khi có yêu cầu, thêm một Maven profile `container`. **Chèn fragment sau trước thẻ đóng `</project>`** trong POM mục 8, không tạo project root thứ hai:

~~~xml
<profiles>
    <profile>
        <id>container</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>create-image-at-package</id>
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

Ý nghĩa:

1. `<id>container</id>` là Maven profile ID, chỉ active khi dùng `-Pcontainer` hoặc một điều kiện được cấu hình chủ động.
2. Plugin cùng coordinates được Maven merge với cấu hình `image.name` đã có ở `<build>`.
3. `<phase>package</phase>` xác định thời điểm Maven chạy execution.
4. `<goal>build-image-no-fork</goal>` tạo OCI image **trong lifecycle đang chạy**, không fork một package lifecycle phụ.
5. `<id>create-image-at-package</id>` giúp truy vết execution trong Maven logs.
6. Vì không đặt `activeByDefault`, `mvn package` bình thường không tự bật build-image.

### 10.1. Build thường, không cần Docker

~~~bash
./mvnw clean package
~~~

Chỉ build/test/package ứng dụng theo lifecycle và plugin defaults; image goal trong profile không được kích hoạt.

### 10.2. Build image khi bật profile

Linux/macOS:

~~~bash
./mvnw -Pcontainer clean package
~~~

PowerShell:

~~~powershell
.\mvnw.cmd -Pcontainer clean package
~~~

Execution no-fork chạy tại `package`. Kiểm tra:

~~~bash
docker image inspect docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT
~~~

**Không thêm `spring-boot:build-image` vào sau lệnh `-Pcontainer package`**. Profile đã bind image goal; thêm một goal khác có thể gây build image lặp.

### 10.3. Ví dụ cấu hình sai

Không dùng:

~~~xml
<execution>
    <id>wrong-goal-on-package</id>
    <phase>package</phase>
    <goals>
        <goal>build-image</goal>
    </goals>
</execution>
~~~

Bởi `build-image` tự fork package, đặt nó trong package execution sẽ làm lifecycle lồng nhau hoặc chạy thêm những goals không cần thiết. Không kết luận mọi version Maven đều lặp vô hạn; điều chắc chắn là **đây không phải cách Spring Boot plugin khuyến nghị**.

Thay bằng:

~~~xml
<execution>
    <id>create-image-at-package</id>
    <phase>package</phase>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

## 11. Các tổ hợp lệnh thường gặp

| Lệnh | Điều sẽ xảy ra theo mô hình ví dụ |
| --- | --- |
| `./mvnw clean package` | Package JAR, không tạo OCI image nếu profile không active |
| `./mvnw spring-boot:build-image` | Goal riêng fork package, tạo OCI image |
| `./mvnw clean spring-boot:build-image` | Clean rồi fork package, tạo image |
| `./mvnw -Pcontainer clean package` | Maven package, no-fork execution tạo image |
| `./mvnw -Pcontainer clean test` | Dừng trước package, chưa có image execution |
| `./mvnw -Pcontainer clean verify` | Qua package nên image được tạo **trước khi verify hoàn tất** |
| `./mvnw package spring-boot:build-image` | Có thể chạy package lặp, không nên dùng mặc định |
| `./mvnw -Pcontainer spring-boot:build-image` | Có thể tạo image hai lần vì goal fork package có execution no-fork trong profile |
| `./mvnw spring-boot:build-image-no-fork` | Không được khuyên dùng riêng khi chưa package, rủi ro artifact cũ/thiếu |
| `./mvnw -Pcontainer -Dspring-boot.build-image.skip=true clean package` | Vẫn package ứng dụng nhưng skip image goal |

**Không nhầm Maven profile với Spring runtime profile.** `-Pcontainer` quyết định Maven plugin execution có chạy không. `spring.profiles.active=prod` quyết định Spring application beans/config khi runtime; nó không thay đổi hành vi fork package.

## 12. Repackage, effective POM và ordering

Khi dự án kế thừa Spring Boot Starter Parent, `repackage` execution có thể được parent cấu hình vào packaging lifecycle. Nếu bạn thêm no-fork execution cũng ở package, Spring Boot plugin được thiết kế để có thể xử lý tình huống này; image goal còn có khả năng repackage nếu cần.

Để xem các executions đã merge từ parent, profile và module:

~~~bash
./mvnw -Pcontainer help:active-profiles
./mvnw -Pcontainer help:effective-pom -Doutput=effective-pom.xml
~~~

`effective-pom.xml` là output để **kiểm tra**, không phải file cần sửa. Chỉnh `pom.xml` nguồn nếu muốn thay đổi.

Sơ đồ mong đợi:

~~~text
Maven lifecycle đến package
          |
          +-- Maven JAR/WAR packaging
          |
          +-- Spring Boot repackage (nếu được bind)
          |
          +-- build-image-no-fork (profile container)
          |
          v
        OCI image
~~~

**Đừng suy luận chính xác thứ tự các executions chỉ từ sơ đồ** trong dự án có corporate parent/multiple plugins. Maven có quy tắc plugin/goal ordering riêng; xem effective POM và Maven log thật. Cũng đừng khai báo hai `repackage` goals trùng hoặc classifiers mâu thuẫn chỉ vì nghĩ image goal yêu cầu.

### Multi-module Maven reactor

Ví dụ:

~~~text
company-parent/
├── pom.xml                   (packaging=pom)
├── common-library/pom.xml    (packaging=jar, không có Spring main)
└── web-app/pom.xml           (packaging=jar, Spring Boot app)
~~~

Chỉ application module như `web-app` nên tạo image. Một execution đặt ở parent `<build><plugins>` có thể lan tới các child modules hoặc cố tạo image cho một library không có main class.

Khuyến nghị: quản lý versions chung ở `<pluginManagement>`, còn image execution đặt trong đúng application module hoặc profile có kiểm soát. Nếu nhiều ứng dụng, đặt image names khác nhau. Kiểm tra Maven reactor logs trước khi triển khai cho toàn bộ monorepo.

## 13. CI và điểm cần chú ý với verify

Image goal bind `package` có thể thực thi **trước khi integration tests/quality gates ở verify hoàn tất**.

~~~text
compile -> test -> package -> integration-test -> verify
                     |
                     +-- build-image-no-fork
                         khi execution ở package
~~~

Ví dụ:

~~~bash
./mvnw -Pcontainer clean verify
~~~

Maven đi qua package và tạo image, sau đó mới qua `integration-test`/`verify`. Nếu một integration test fail, image có thể đã tồn tại local, nhưng **không được publish/deploy image như một release đã đạt QA**.

### Chiến lược A: package image, gate publish

1. Chạy `./mvnw -Pcontainer clean verify`.
2. Image được xây tại package nhưng CI chỉ tiến tới bước tiếp theo nếu verify pass.
3. Chạy HTTP smoke test trong container, scan CVEs/SBOM và kiểm tra provenance.
4. Publish/deploy image theo digest **chỉ sau mọi gate**.
5. Nếu verify fail, không push và không triển khai.

Ưu điểm là dễ kết hợp Maven lifecycle, nhược điểm là vẫn tiêu chi phí build image ngay cả khi tests sau package fail.

### Chiến lược B: verify trước, build image sau

1. Gọi `./mvnw clean verify` **không active image profile**.
2. Nếu pass, chạy `./mvnw spring-boot:build-image` ở CI stage riêng.
3. Nhớ rằng `build-image` sẽ fork package, nên có thể lặp compiler/tests/packaging đã chạy.
4. Kiểm soát input và archive checksum nếu yêu cầu image xây từ **đúng bytes artifact đã verify**.
5. Smoke test, scan và publish bằng image digest bất biến.

Khi cần tránh cả việc re-run package, có thể thiết kế một **no-fork execution ở pha muộn hơn** trong pipeline đã kiểm soát ordering, hoặc quy trình consume artifact đã lưu. Nhưng không nên giả định cùng source commit là đủ cho byte-for-byte identity nếu build có timestamp/dynamic dependency.

### Chuyển no-fork execution tới verify?

Có thể cấu hình:

~~~xml
<execution>
    <id>create-image-on-verify</id>
    <phase>verify</phase>
    <goals>
        <goal>build-image-no-fork</goal>
    </goals>
</execution>
~~~

Đây là **phương án thay thế execution package**, không nên giữ cả hai cùng active. Nếu Failsafe verify và image goal cùng ở pha `verify`, thứ tự thực tế của plugin executions cần được xác nhận. Khi thứ tự không rõ, dùng CI stages riêng để bảo đảm image chỉ build sau quality gates.

## 14. Cấu hình CNB image, builder và run image

Hai goals dùng các thông số CNB tương tự nhau. Ví dụ **fragment cấu hình plugin** (không thêm plugin thứ hai trùng coordinates):

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <name>docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT</name>
            <builder>paketobuildpacks/builder-jammy-base:latest</builder>
        </image>
    </configuration>
</plugin>
~~~

Tài liệu Spring Boot 3.3 mô tả Paketo builder dạng `paketobuildpacks/builder-jammy-base:latest`; **tag latest không phải digest bất biến**. Production nên quản lý builder/run image versions và chính sách cập nhật bảo mật. Đừng pin một image có lỗ hổng vô thời hạn chỉ để giữ cache.

| Cấu hình | Vai trò |
| --- | --- |
| `image.name` | Tên/tag output OCI image |
| `image.builder` | Builder image cho CNB lifecycle |
| `image.runImage` | Run image nếu cần điều khiển riêng |
| `image.env` | Environment values cho buildpacks (ví dụ Java runtime policy) |
| `image.pullPolicy` | Khi nào pull builder/run image |
| `image.cleanCache` | Có chủ đích xóa cache để điều tra |
| `image.publish` | Khi bật mới publish image lên registry |
| `image.verboseLogging` | Thêm thông tin hoạt động buildpacks |

**Default `publish=false`:** image local có thể chạy được nhưng chưa hề được push lên registry. Không hard-code registry credentials trong POM.

### Override image tag bằng CLI

Linux/bash:

~~~bash
./mvnw -Dspring-boot.build-image.imageName=demo-local:0.0.1 \
    spring-boot:build-image
~~~

PowerShell:

~~~powershell
.\mvnw.cmd "-Dspring-boot.build-image.imageName=demo-local:0.0.1" spring-boot:build-image
~~~

Khi override, dùng tên `demo-local:0.0.1` với `docker image inspect`, không tiếp tục tìm tag cũ trong POM.

### CNB cache không phải Maven cache

Buildpacks có cache các layers/phần runtime, khác hoàn toàn với Maven local dependency repository `~/.m2/repository`. CI runner mới, builder mới hoặc cache volume bị xóa có thể khiến image build lâu hơn mặc dù source không đổi. Đọc logs thực tế, không gán mọi sự chậm đi cho việc chọn build-image thay vì no-fork.

## 15. Skip image, skip tests và quyền publish

Nếu profile image active nhưng muốn build JAR mà không chạy Docker:

~~~bash
./mvnw -Pcontainer -Dspring-boot.build-image.skip=true clean package
~~~

Property `spring-boot.build-image.skip` điều khiển **image goal**, không bỏ qua compile/test/package. Nó cũng không xóa Docker image đã tạo từ lần build trước.

Khác với:

~~~bash
./mvnw -Pcontainer -DskipTests clean package
~~~

`-DskipTests` thường bỏ qua chạy unit tests, **không phải** tắt CNB image goal. Tránh tạo/publish production image chưa qua tests chỉ để rút ngắn thời gian build.

**Registry publishing** là quyết định riêng: `docker image inspect` thành công chỉ xác nhận image tồn tại trong Docker daemon hiện tại. Publish cần image registry, credentials, quyền truy cập và một bước push hoặc `image.publish=true` được kiểm soát. Nếu plugin và Docker CLI dùng các Docker contexts khác nhau, bạn có thể nhìn nhầm daemon; kiểm tra `docker context ls` cùng Docker API settings.

## 16. Các lệnh kiểm chứng cho CI

Một kịch bản Linux/bash **minh họa** khi bạn chủ động tạo image tại package nhưng muốn gate trước khi publish:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Image tạo tại package; verify tiếp tục chạy các tests/gates sau đó.
./mvnw -B -ntp -Pcontainer clean verify

# Script chỉ đi tiếp nếu Maven verify thành công.
IMAGE='docker.io/library/cnb-maven-demo:0.0.1-SNAPSHOT'
docker image inspect "$IMAGE" > /dev/null

echo "VERIFY_AND_IMAGE_PRESENT"
~~~

Nếu verify pass và image nằm trong daemon hiện tại, stdout do câu lệnh cuối in:

~~~text
VERIFY_AND_IMAGE_PRESENT
~~~

**Giới hạn:** script xác minh Maven verify và image hiện diện, nhưng **chưa chạy HTTP smoke test, SBOM/CVE scan, signature hay publish gate**. Chúng phải được thêm vào pipeline release thực tế. Nếu verify fail, có thể image đã được build trước đó trong package phase nhưng script sẽ không in PASS.

Để test container qua HTTP, có thể chạy image bằng `docker run` và gọi `/ping` sau khi server ready. Trong CI automation, nên start detached, poll endpoint có timeout giới hạn, ghi logs và cleanup container cả khi test fail. Không dùng một lần `sleep 1` rồi mặc định ứng dụng đã khởi động.

**Không suy luận build image thành công thì mọi tích hợp runtime đều hoạt động.** JUnit `@WebMvcTest` và container smoke test kiểm tra hai lớp khác nhau.

## 17. Troubleshooting: thường sai ở mục nào?

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| CLI build-image chạy compile/test/package | Đó là **fork lifecycle theo thiết kế** | Không coi là bug; dùng goal đúng cho CLI |
| Package xuất hiện hai lượt trong Maven log | Bind nhầm build-image vào package hoặc dùng package + build-image | Đổi sang build-image-no-fork trong execution |
| `-Pcontainer package` không tạo OCI image | Profile không active, XML không hợp lệ, execution bị skip | Kiểm tra active-profiles, effective POM, logs |
| `mvn package` bình thường đột nhiên cần Docker | Image execution được gắn vào build mặc định | Chuyển sang opt-in profile container |
| CLI no-fork sau clean báo thiếu archive | No-fork không fork lifecycle chuẩn bị package | Dùng build-image trực tiếp |
| Image đã có nhưng verify test fail | Image goal ở package, test ở phase sau | Không publish; sửa CI gating |
| Docker daemon connection failed | Docker Engine/Desktop chưa chạy hoặc socket/context sai | `docker info`, `docker context ls`, permissions |
| Builder/run image không tải được | Registry auth, proxy, DNS, mạng hoặc pull policy | Kiểm tra mirror và quyền truy cập |
| Runtime Java version không tương thích | Maven compiler target/builder Java khác | Đồng bộ Java 17 và CNB runtime config |
| Không xác định main class | Module library không có main hoặc nhiều main classes | Dùng đúng app module, chọn mainClass |
| JAR có no main manifest attribute | Chọn plain JAR chưa Boot repackage | Xem Maven artifact và Spring Boot Maven Plugin |
| Inspect không thấy image ở tên mong đợi | image.name/CLI override hoặc daemon khác | Đọc image name trong logs và context |
| Có Dockerfile nhưng chỉnh không ảnh hưởng CNB image | CNB goal không chạy Dockerfile | Dùng Dockerfile pipeline nếu cần |
| Tất cả child module đều tạo image | Parent plugin execution bị inherit | Chỉ bind trong app module |
| Builder liên tục tải dependency dù source không đổi | Cache lạnh, image builder thay đổi, dynamic dependencies | Kiểm tra cache store, version và logs |
| `spring-boot.build-image.skip=true` nhưng image vẫn trong daemon | Skip không xóa image cũ | So sánh logs của lượt hiện tại |
| Docker publish báo 401/403 | Thiếu registry credentials/quyền | Dùng CI secret store và namespace hợp lệ |
| Image chạy nhưng GET /ping fail | Controller/config/port/runtime chưa đúng | Xem container logs và endpoint thực |

### Trình tự điều tra

1. Đọc **command line**: có đang gọi một lifecycle phase hay plugin goal trực tiếp?
2. Xem effective POM/profile: `build-image` hay `build-image-no-fork` được gắn vào phase nào?
3. Kiểm tra JAR ở `target` và Java main class/Boot manifest.
4. Kiểm tra Docker daemon, CNB builder, run image, network và auth.
5. Đọc logs detect/build/export, không chỉ lỗi cuối.
6. Xem image tag đúng, `docker image inspect` và `docker run`.
7. Gọi HTTP `/ping` và xác nhận response `pong`.
8. Xác nhận integration tests ở verify pass trước khi publish.
9. Sửa đúng lớp gây lỗi, không đổi đồng thời Java version, Maven phase, Docker daemon và builder.

## 18. Bài thực hành và tiêu chí hoàn thành

Làm trên một branch thử nghiệm của Spring Boot Maven project:

1. Tạo `CnbMavenDemoApplication`, `PingController`, `PingControllerTest` và `pom.xml` ở các mục 7–8.
2. Dùng `java -version`, `mvnw --version`, `docker info` để xác minh JDK/Maven/Docker.
3. Chạy `./mvnw clean package`; xác minh executable JAR trong `target`, không cần tạo image.
4. Chạy `./mvnw spring-boot:build-image`; đọc logs để chỉ ra package lifecycle fork và CNB build.
5. Dùng `docker image inspect` và `docker run`; kiểm tra `GET /ping` trả `pong`.
6. Thêm Maven profile `container` có execution `build-image-no-fork` gắn `package`.
7. Chạy `./mvnw -Pcontainer clean package`; xác minh image goal nằm trong package lifecycle **không fork package lần nữa**.
8. Gọi `./mvnw clean package` không active profile và giải thích vì sao image không được tạo.
9. Thử `-Dspring-boot.build-image.skip=true`, xác nhận Maven vẫn package mà image goal bỏ qua.
10. Đọc `help:effective-pom` để kiểm tra execution sau khi merge từ parent/profile.
11. Chạy `./mvnw -Pcontainer clean verify`, xác định image có thể được tạo trước khi verify hoàn tất.
12. Nếu là multi-module project, kiểm tra chỉ ứng dụng web có image execution.
13. Ghi rõ image tag/digest, Docker context, builder/run image, Maven/Boot/Java versions, test report và kết quả HTTP smoke.
14. Giải thích tác động khi bind nhầm `build-image` vào package.
15. Kết luận quy trình tổ chức nên chọn CLI goal, opt-in lifecycle profile hay CI stages tách biệt.
16. Khôi phục cấu hình thử nghiệm trước khi kết thúc và không tự publish image chưa được scan/approved.

**Đạt yêu cầu khi:** bạn hiểu cơ chế Maven lifecycle fork, xây được OCI image bằng **CLI `build-image`** lẫn **lifecycle-bound `build-image-no-fork`**, không chạy image goal dư thừa và chỉ publish/deploy sau quality gates.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Maven Plugin: Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html)
- [Spring Boot 3.3 – Maven Plugin: Goals](https://docs.spring.io/spring-boot/3.3/maven-plugin/goals.html)
- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven – Introduction to Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven – Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Cloud Native Buildpacks – Concepts](https://buildpacks.io/docs/for-app-developers/concepts/)
- [Cloud Native Buildpacks – Specification](https://github.com/buildpacks/spec)
- [Paketo Buildpacks – Documentation](https://paketo.io/docs/)
- [Docker Docs – Docker Engine](https://docs.docker.com/engine/)
