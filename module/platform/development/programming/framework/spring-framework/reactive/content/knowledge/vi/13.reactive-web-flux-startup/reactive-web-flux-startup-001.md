# Chuẩn bị phiên bản Spring, Reactor và thư viện máy chủ tương thích

## 1. Mục tiêu: chọn một bộ phiên bản hoạt động như một hệ thống

Một ứng dụng Spring WebFlux thường có nhiều lớp thư viện cùng tham gia:

- **Java/JDK**: phiên bản runtime, compiler và bytecode target.
- **Spring Boot** (nếu dùng): cấu hình, auto-configuration, starter và danh sách dependency được kiểm thử cùng nhau.
- **Spring Framework**: Spring WebFlux, codec, HTTP abstractions và dependency injection.
- **Project Reactor**: Reactor Core, Mono, Flux, Scheduler và operator.
- **Reactor Netty** (nếu chọn): HTTP/TCP client và server bất đồng bộ dựa trên Netty.
- **Netty**: transport, codec, resolver, handler và native transport khi cần.
- **Máy chủ thay thế**: Tomcat hoặc Jetty cũng có thể chạy WebFlux qua adapter non-blocking phù hợp.

Các thành phần này có **chu kỳ phát hành và cách đánh số phiên bản riêng**. Không thể suy ra Reactor Core phải có cùng số major với Spring Framework, hoặc Reactor Netty phải có cùng số phiên bản với Reactor Core. Điều cần bảo đảm là **tổ hợp phiên bản được hỗ trợ và kiểm thử với nhau**.

Với ứng dụng dùng Spring Boot, cách ổn định nhất là chọn một bản Boot phù hợp với JDK mục tiêu và để **Spring Boot dependency management (BOM)** quản lý phiên bản Spring Framework, Reactor, Reactor Netty, Netty cùng các thư viện liên quan. Chỉ override một phiên bản khi có lý do tương thích hoặc bảo mật cụ thể, đã kiểm tra dependency graph và chạy test.

## 2. Sơ đồ dependency và trách nhiệm

~~~text
Ứng dụng Java
    |
    +-- Spring Boot (nếu dùng)
    |      +-- dependency management / BOM
    |      +-- auto-configuration và starter
    |
    +-- Spring Framework
    |      +-- spring-webflux
    |      +-- codec / HTTP handler / WebClient
    |
    +-- Project Reactor
    |      +-- reactor-core: Mono, Flux, Scheduler
    |      +-- reactor-test: StepVerifier
    |
    +-- Runtime HTTP server (chọn một)
           |
           +-- Reactor Netty
           |      +-- Netty transport / codec / resolver
           |
           +-- Tomcat (Servlet non-blocking adapter)
           |
           +-- Jetty (Servlet non-blocking adapter)
~~~

**Spring WebFlux là framework web reactive, không phải một HTTP server độc lập.** Spring Boot WebFlux starter tự động ghép các thành phần cần thiết và mặc định dùng Reactor Netty; Tomcat và Jetty cũng là lựa chọn hợp lệ. Vì vậy, phải kiểm tra cả phiên bản server và các dependency nền của nó.

Một cách đọc dependency tree:

- `spring-boot-starter-webflux` là dependency cấp ứng dụng.
- `spring-webflux` là module của Spring Framework.
- `reactor-core` là thư viện thực thi Mono/Flux.
- `reactor-netty-http` là HTTP runtime dựa trên Reactor Netty.
- `io.netty:*` là các module Netty ở tầng mạng.

Nếu dependency graph chứa hai phiên bản `reactor-core` hoặc nhiều phiên bản Netty do override/transitive dependency, cần xác định version thực sự được chọn và lý do trước khi triển khai.

## 3. Hiểu version line trước khi chọn dependency

### 3.1. Chọn Java trước

Java là điều kiện nền của cả quá trình build và chạy:

1. JDK dùng trên máy lập trình.
2. JDK mà Maven/Gradle daemon thực sự sử dụng.
3. Java release/bytecode target của dự án.
4. JRE/JDK trong container hoặc máy chủ production.
5. Phiên bản Java tối thiểu của các thư viện bên thứ ba.

Ví dụ, compiler có thể tạo bytecode Java 21 nhưng production chỉ có Java 17. Khi đó ứng dụng có thể gặp `UnsupportedClassVersionError` lúc khởi động, dù quá trình build trên máy developer thành công.

Tại thời điểm soạn bài, tài liệu Spring Boot 4.1.2 quy định **Java tối thiểu 17**, hỗ trợ đến Java 27 và yêu cầu **Spring Framework 7.0.10 trở lên**. Maven được hỗ trợ từ 3.6.3; Gradle 8.x cần ít nhất 8.14 hoặc dùng Gradle 9.x. Dependency bên thứ ba có thể yêu cầu Java cao hơn. Hãy đọc trang System Requirements của đúng phiên bản Boot đang chọn thay vì áp dụng con số của một release cũ.

### 3.2. Các dòng phiên bản phải đi cùng nhau

| Nền tảng | Dòng phiên bản cần đối chiếu | Cách quyết định |
| --- | --- | --- |
| Spring Boot 4.1.2 | Java 17+; Spring Framework 7.0.10+ | Dùng Boot BOM cho các thư viện Spring và Reactor |
| Spring Boot 3.x | Java 17+; Spring Framework 6.x tùy minor release | Dùng BOM đúng bản Boot 3.x đang chọn; không lấy dependency của Boot 4 ghép vào |
| Spring Framework không dùng Boot | Spring Framework BOM và yêu cầu Java của release tương ứng | Tự quản lý Reactor và server runtime theo tài liệu tương thích của từng dự án |
| Reactor Core | Version độc lập theo Reactor release train | Dùng phiên bản được BOM của nền tảng quản lý |
| Reactor Netty và Netty | Version độc lập, có quan hệ tương thích giữa các module | Giữ các module Netty đồng bộ theo BOM/khuyến nghị của Reactor Netty |

Bảng này chỉ ra **cách chọn version line**, không phải quy tắc rằng mọi patch release có thể ghép tùy ý. Với Spring Boot, bảng Managed Dependency Coordinates của chính release Boot là nguồn xác định version cụ thể của `spring-webflux`, `reactor-core`, `reactor-netty-http` và Netty.

**Không lấy phiên bản mới nhất riêng lẻ của từng thư viện rồi ghép vào một ứng dụng đang dùng Boot cũ.** Bản mới của Reactor Netty có thể yêu cầu Reactor Core hoặc Netty khác với những gì release Boot hiện tại quản lý.

### 3.3. BOM là gì?

BOM (Bill of Materials) là một POM dùng để quản lý các phiên bản dependency có liên quan. Khi dự án import BOM, dependency được khai báo có thể **không cần version riêng**; Maven/Gradle lấy version từ dependency management.

Spring Boot cung cấp BOM `spring-boot-dependencies`. BOM này quản lý các module Spring Framework, Reactor, Reactor Netty, Netty và nhiều thư viện khác theo một bộ phiên bản đã được chọn cùng nhau.

Phân biệt:

- **Dependency declaration**: dự án thực sự cần thư viện nào.
- **Dependency management**: phiên bản nào được chọn khi thư viện được khai báo.
- **Transitive dependency**: thư viện được kéo vào thông qua một dependency khác.
- **Version override**: dự án chủ động thay version mặc định của BOM.
- **Dependency convergence**: cùng một artifact không bị chọn nhiều version xung đột trong graph.

Import BOM không tự thêm tất cả thư viện vào classpath. Nó cung cấp quy tắc phiên bản; dự án vẫn khai báo những starter/module cần dùng.

## 4. Cách ưu tiên khi dự án sử dụng Spring Boot

Với ứng dụng WebFlux mới, bắt đầu bằng các quyết định:

1. Chọn Spring Boot release còn phù hợp với chính sách hỗ trợ và JDK của môi trường.
2. Đặt JDK/toolchain cùng bytecode target theo yêu cầu production.
3. Thêm `spring-boot-starter-webflux`.
4. Để Boot BOM chọn Spring Framework, Reactor Core, Reactor Netty và Netty.
5. Chỉ chọn server khác khi có yêu cầu triển khai rõ ràng.
6. Kiểm tra dependency tree, build và chạy kiểm thử tích hợp.

**Không cần khai báo riêng version của `spring-webflux`, `reactor-core` và `reactor-netty-http`** khi những dependency này đã được Boot quản lý. Khai báo thủ công dễ tạo một tổ hợp lệch khỏi bộ dependency được kiểm thử của Boot.

## 5. Ví dụ Maven: Spring Boot 4.1.2 + WebFlux + Reactor Netty mặc định

Ví dụ sau dùng **Java 17+**, **Maven 3.6.3+** và Spring Boot 4.1.2. Phiên bản 4.1.2 là phiên bản minh họa theo tài liệu hiện hành tại thời điểm soạn bài; với dự án thực tế, chọn patch release được tổ chức hỗ trợ và cập nhật bảo mật.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>webflux-version-check</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Ở đây chỉ có version của **Spring Boot parent**. Starter WebFlux không khai báo version; các dependency transitive như Spring Framework, Reactor Core và Reactor Netty được quản lý qua Boot BOM.

### Ví dụ ứng dụng

Tạo file `src/main/java/com/example/compat/WebfluxVersionCheckApplication.java`:

~~~java
package com.example.compat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxVersionCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxVersionCheckApplication.class, args);
    }
}
~~~

Tạo file `src/main/java/com/example/compat/ProbeController.java`:

~~~java
package com.example.compat;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ProbeController {

    @GetMapping("/ping")
    public Mono<String> ping() {
        return Mono.just("webflux-ready");
    }

    @GetMapping("/numbers")
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
~~~

Khởi động:

~~~bash
mvn -version
java -version
mvn clean package
mvn spring-boot:run
~~~

Ở terminal khác, gọi endpoint:

~~~bash
curl -s http://localhost:8080/ping
curl -s http://localhost:8080/numbers
~~~

Body response dự kiến:

~~~text
webflux-ready
[1,2,3]
~~~

Kết quả cho thấy classpath đã đủ để chạy Spring WebFlux và Reactor. Tuy nhiên, **một endpoint hoạt động chưa chứng minh toàn bộ dependency graph đã an toàn cho production**; cần xem dependency tree, chạy test và kiểm tra runtime thật.

## 6. Ví dụ Gradle: để Spring Boot plugin quản lý dependency

Nếu dùng Gradle Groovy DSL, cấu hình tương đương:

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Khi áp dụng plugin dependency management cùng Spring Boot plugin, Boot tự import BOM tương ứng; dependency được quản lý có thể khai báo không kèm version.

Nếu dùng native Gradle BOM support, có thể khai báo platform của Spring Boot dependency BOM trong dependencies:

~~~groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Chỉ cần chọn **một cách quản lý phiên bản rõ ràng** và kiểm tra kết quả resolution. Không nên vừa dùng nhiều BOM có ràng buộc mâu thuẫn, vừa ép version riêng trên từng artifact mà không có kế hoạch.

Kiểm tra dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

`dependencyInsight` cho biết dependency được chọn, các đường dẫn kéo nó vào và vì sao một version được ưu tiên.

## 7. Chọn Reactor Netty, Tomcat hay Jetty?

### 7.1. Khi nào giữ Reactor Netty mặc định?

`spring-boot-starter-webflux` mặc định đưa Reactor Netty vào làm reactive server. Đây là lựa chọn phù hợp cho phần lớn ứng dụng WebFlux khi:

- Muốn runtime non-blocking dựa trên Netty.
- Muốn dùng chung hệ sinh thái Reactor cho server và WebClient.
- Không có ràng buộc triển khai bắt buộc phải dùng một Servlet container khác.
- Muốn giữ cấu hình starter và version management đơn giản.

Boot có thể tạo tài nguyên Reactor Netty cho server và chia sẻ một số tài nguyên với WebClient được auto-configure trong những điều kiện phù hợp. Không nên tạo thêm client/server resource pool tùy tiện nếu chưa hiểu lifecycle và mục tiêu cấu hình.

### 7.2. Khi nào dùng Tomcat hoặc Jetty?

Spring WebFlux có adapter cho Servlet non-blocking I/O nên có thể chạy trên **Tomcat hoặc Jetty**. Điều này hữu ích nếu môi trường triển khai đã chuẩn hóa một container, có yêu cầu vận hành hoặc công cụ giám sát riêng.

Tuy nhiên, dùng Tomcat/Jetty với WebFlux **không có nghĩa ứng dụng trở thành Spring MVC**. Programming model vẫn là WebFlux; cách server đọc/ghi network và tích hợp với HTTP handler thay đổi theo runtime.

### 7.3. Thay Reactor Netty bằng Tomcat trong Maven

Nếu muốn dùng Tomcat reactive runtime, loại starter Reactor Netty và thêm starter Tomcat do Boot quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
~~~

Với Jetty, thay dependency Tomcat bằng starter Jetty tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

Đây là **phần cấu hình dependency thay thế**, không phải toàn bộ pom.xml. Giữ version do Boot BOM quản lý. Sau khi đổi server, chạy lại `mvn dependency:tree` để chắc chắn Reactor Netty không còn được kéo vào như server runtime ngoài chủ đích, đồng thời kiểm tra những dependency khác vẫn có thể cần Reactor Netty làm HTTP client.

**Đừng thêm cả Reactor Netty, Tomcat và Jetty như ba server mặc định** nếu ứng dụng chỉ cần một server. Nhiều runtime cùng có mặt có thể làm auto-configuration khó dự đoán hoặc khiến ứng dụng kéo thêm dependency không cần thiết.

### 7.4. Tránh nhầm MVC và WebFlux

Spring MVC và Spring WebFlux có thể cùng tồn tại trong hệ sinh thái Spring, nhưng ứng dụng cần xác định **web application type** rõ ràng. Spring Boot có hành vi ưu tiên MVC khi đồng thời có cả MVC và WebFlux starter trong một số cấu hình mặc định; trường hợp phổ biến là ứng dụng MVC chỉ thêm WebFlux để sử dụng WebClient.

Nếu mục tiêu là một reactive server:

- Giữ dependency WebFlux và server reactive phù hợp.
- Loại MVC starter nếu không cần.
- Nếu có lý do giữ cả hai, cấu hình application type rõ ràng, ví dụ `spring.main.web-application-type=reactive`, và xác minh auto-configuration lúc chạy.

Không kết luận ứng dụng đã chạy WebFlux chỉ vì source code có `Mono` hoặc `Flux`. Hãy kiểm tra log khởi động, web application type và runtime server thực tế.

## 8. Nếu không dùng Spring Boot thì quản lý thế nào?

Một ứng dụng Spring Framework thuần vẫn có thể dùng WebFlux, Reactor và một HTTP server tương thích. Khi không có Boot BOM, nhóm phát triển phải tự quản lý các version line.

Cách tiếp cận:

1. Chọn **Spring Framework release** và kiểm tra yêu cầu Java cùng các server runtime được hỗ trợ trong tài liệu của release đó.
2. Dùng Spring Framework BOM để các module Spring như `spring-webflux` và `spring-web` có cùng version line.
3. Chọn **Reactor Core** theo Reactor release train tương thích với ứng dụng; `reactor-test` phải theo cùng version line với Reactor Core.
4. Chọn **Reactor Netty** theo release documentation/BOM của chính Reactor Netty và đảm bảo các module Netty được quản lý nhất quán.
5. Nếu chọn Tomcat/Jetty, kiểm tra Servlet API, Jakarta namespace và yêu cầu của server version.
6. Chạy test tích hợp thực tế với JDK, server và dependency graph cuối cùng.

Không có một con số chung kiểu “Spring 7 thì Reactor phải 7”. Các dự án có chu kỳ phát hành riêng. Hãy dùng BOM chính thức và bảng hỗ trợ của từng release để xác định tổ hợp cụ thể, thay vì tự ghép version theo số major.

## 9. Kiểm tra version thực sự được Maven resolve

Khai báo trong pom.xml chỉ là **yêu cầu đầu vào**; version chạy thực tế phải được xác nhận từ effective POM và dependency graph.

### 9.1. Xem JDK mà Maven đang dùng

~~~bash
java -version
javac -version
mvn -version
~~~

`mvn -version` cho biết Java mà Maven process sử dụng. Nếu Maven chạy trên một JDK khác với `java` ở terminal, hãy thống nhất toolchain/IDE/CI để tránh “máy tôi build được”.

### 9.2. Xem effective POM

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM là kết quả sau khi Maven hợp nhất parent POM, properties, dependency management và cấu hình plugin. Dùng nó để xem version nào thực sự được Boot BOM đưa vào.

### 9.3. Xem dependency tree

~~~bash
mvn dependency:tree -Dverbose
~~~

Có thể lọc những nhóm quan trọng:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework:*,io.projectreactor:*,io.projectreactor.netty:*,io.netty:*
~~~

Tập trung kiểm tra:

- Chỉ một version phù hợp của `spring-webflux` và các module Spring liên quan.
- `reactor-core` và `reactor-test` cùng version line.
- `reactor-netty-core` và `reactor-netty-http` cùng version line của Reactor Netty.
- Các module `io.netty` không bị ép thành những version xung đột.
- Không có dependency cũ kéo lại một module Spring/Reactor ngoài ý muốn.
- Không có exclusion loại nhầm một thư viện runtime cần thiết.

Từ khóa `omitted for conflict` trong dependency tree cho biết Maven đã bỏ một đường dependency do chọn version khác; đó không phải lúc nào cũng là lỗi, nhưng cần hiểu vì sao version đó được chọn.

### 9.4. Kiểm tra runtime classpath của Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
~~~

Khi Gradle dùng version catalog, platform hoặc constraints, cần kiểm tra **version được resolve cuối cùng**, không chỉ đọc version alias trong `libs.versions.toml`.

## 10. Dấu hiệu của một bộ version không tương thích

| Triệu chứng | Nguyên nhân có thể gặp | Hướng kiểm tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Bytecode được compile bằng Java mới hơn JDK runtime | So sánh `mvn -version`, toolchain, release target và container JRE |
| `NoSuchMethodError` | Runtime nạp version cũ của class dù compile với version mới | Dependency tree, BOM override và thư viện transitive |
| `NoClassDefFoundError` / `ClassNotFoundException` | Thiếu module hoặc dependency bị exclusion sai | Runtime dependency tree, packaging và classpath |
| `LinkageError` | Các module cùng họ không tương thích binary | Kiểm tra version Spring/Reactor/Netty đã resolve |
| Ứng dụng khởi động nhầm MVC | Có MVC starter cùng WebFlux hoặc web application type không đúng | Starter list, application type và auto-configuration |
| Không tạo được reactive server | Server starter bị loại hoặc thiếu runtime phù hợp | Dependency tree, log auto-configuration |
| Lỗi method/class của Netty | Module Netty lệch version hoặc native transport không tương thích | Các artifact `io.netty`, classifier và OS/architecture |
| Test compile nhưng production fail | Test classpath khác runtime hoặc container dùng JDK khác | Chạy integration test trên cùng image/JDK/dependency profile |

Một stack trace có `NoSuchMethodError` không có nghĩa method vừa bị xóa khỏi code đang viết. Thường compiler đã thấy một version có method đó nhưng runtime lại nạp một version khác. Vì vậy cần đọc dependency tree và kiểm tra artifact được đóng gói.

### 10.1. Không tự override từng module Netty

Reactor Netty dùng nhiều module Netty: transport, codec, handler, resolver và các module khác. Nếu chỉ override `netty-codec-http` nhưng để `netty-handler` và `netty-transport` ở version khác, lỗi binary có thể xuất hiện rất khó truy vết.

Khi phát hiện lỗ hổng bảo mật hoặc bug cần cập nhật Netty:

1. Xác định bản Spring Boot đang dùng có bản vá phù hợp không.
2. Kiểm tra version Netty được Boot BOM quản lý.
3. Đọc khuyến nghị nâng cấp của Spring Boot/Reactor Netty.
4. Chỉ override đồng bộ nhóm dependency được khuyến nghị, có ghi nhận lý do.
5. Chạy test tích hợp, kiểm tra TLS, HTTP/2, WebClient và server runtime nếu ứng dụng sử dụng.

Không dùng `netty-all` hoặc một module Netty mới để “chữa nhanh” khi chưa kiểm tra dependency graph. Việc thêm một artifact không tự làm tất cả module Netty trong ứng dụng tương thích.

## 11. Quy trình nâng cấp version an toàn

Khi cần nâng cấp Spring/Boot/Reactor:

**Bước 1 — ghi lại baseline hiện tại**

- JDK và Maven/Gradle.
- Spring Boot hoặc Spring Framework version.
- Spring WebFlux version.
- Reactor Core, Reactor Test, Reactor Netty và Netty.
- HTTP server đang sử dụng.
- Các dependency override và exclusion.

**Bước 2 — chọn target release line**

- Kiểm tra System Requirements.
- Kiểm tra tình trạng hỗ trợ và security fixes.
- Kiểm tra Java, Jakarta và Servlet requirements.
- Đọc migration/release notes nếu nâng qua major version.

**Bước 3 — nâng version gốc**

Với ứng dụng Boot, thường chỉ cần nâng version Boot parent/plugin; để BOM thay đổi các dependency được quản lý. Không đồng thời sửa hàng loạt version Spring, Reactor, Netty thủ công.

**Bước 4 — kiểm tra dependency graph**

Chạy effective POM/dependency tree hoặc Gradle dependencyInsight. So sánh những artifact thay đổi, tìm version bị override bởi dependency trực tiếp hoặc BOM khác.

**Bước 5 — build và test theo từng lớp**

- Compile và unit tests.
- Application context startup.
- WebFlux integration test.
- Test WebClient gọi HTTP ngoài.
- Test serialization/codec, timeout, cancellation và streaming.
- Test TLS, HTTP/2 hoặc native transport nếu có dùng.
- Smoke test trên container/JDK giống production.

**Bước 6 — triển khai thử và quan sát**

Theo dõi startup logs, connection errors, latency, thread usage, Netty event-loop, memory, GC và lỗi 5xx. Không đánh giá chỉ bằng việc compile thành công.

## 12. Kiểm thử tối thiểu cho ứng dụng WebFlux

Một bộ kiểm tra tối thiểu nên bao gồm:

1. Ứng dụng khởi động đúng web application type.
2. Reactive server bind đúng port.
3. Endpoint trả Mono và Flux được encode đúng.
4. WebClient có thể kết nối dịch vụ ngoài qua runtime đã chọn.
5. Cancellation/timeout/error handling hoạt động như mong đợi.
6. Không có lỗi binary linkage khi chạy trên đúng JDK/container.
7. Dependency graph production tương đương dependency graph đã test.

Ví dụ smoke test thủ công với ứng dụng ở phần Maven:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/numbers
~~~

Kỳ vọng HTTP 200 và body tương ứng:

~~~text
webflux-ready
[1,2,3]
~~~

Với test tự động, dùng WebTestClient và StepVerifier phù hợp với loại endpoint; kiểm tra cả HTTP status/content-type và các tín hiệu reactive. Nếu đổi server từ Reactor Netty sang Tomcat/Jetty, chạy lại integration test trên **server mới** vì một số khác biệt chỉ lộ ra khi có network I/O thật.

## 13. Docker và môi trường triển khai cũng là một phần của compatibility

Một dự án có thể build trên JDK 21 nhưng image runtime dùng Java 17; điều đó chỉ an toàn nếu bytecode target và mọi thư viện đều tương thích Java 17. Ngược lại, dùng image runtime Java mới hơn có thể chạy được bytecode cũ, nhưng cần test đúng môi trường đó.

Ví dụ Dockerfile minh họa dùng Java 17:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/webflux-version-check-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dockerfile này giả định đã build được file jar có tên đúng trong target. Nếu dùng JDK/Boot mới hơn hoặc yêu cầu native libraries, chọn base image phù hợp với JDK, OS và kiến trúc CPU. Native transport Netty cần đúng classifier/platform; không copy native artifact cho một OS sang image khác.

Đảm bảo CI và production cùng cách:

- Chọn JDK runtime.
- Resolve dependency từ cùng pom/lockfile.
- Dùng cùng server starter và profile.
- Không override version chỉ trong production mà không test.
- Build image từ artifact đã được kiểm thử.

## 14. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách làm đúng |
| --- | --- | --- |
| Tự chọn version mới nhất cho Spring, Reactor và Netty riêng lẻ | Lệch bộ phiên bản đã được kiểm thử | Dùng Boot BOM hoặc các BOM tương thích chính thức |
| Khai báo version trực tiếp cho mọi transitive dependency | Dễ tạo xung đột khi nâng Boot | Chỉ override khi có căn cứ và test |
| Chỉ kiểm tra JDK trên máy developer | Maven/Gradle/CI/container có thể dùng JDK khác | Kiểm tra `mvn -version`, toolchain và image runtime |
| Nghĩ Spring WebFlux chính là Reactor Netty | Không hiểu server runtime có thể thay đổi | Tách framework WebFlux và HTTP server |
| Dùng WebFlux starter rồi thêm Tomcat nhưng quên loại Reactor Netty | Kéo hai runtime ngoài ý muốn | Exclude starter server mặc định và thêm server thay thế |
| Có cả MVC và WebFlux starter nhưng không kiểm tra application type | Boot có thể auto-config MVC | Giữ đúng starter hoặc đặt reactive application type có chủ đích |
| Chỉ override một module Netty | Các module còn lại có thể lệch binary | Theo BOM/version set được hỗ trợ |
| Thêm `spring-webflux` thủ công với version khác Boot | Spring Framework module không đồng bộ | Để Boot BOM quản lý module Spring |
| Test trên Reactor Netty nhưng production chạy Tomcat | Bỏ sót lỗi adapter/server | Test đúng server production |
| Chỉ chạy compile/package | Không phát hiện runtime linkage/network problems | Startup và integration tests trên đúng JDK/server |
| Xem `dependency:tree` nhưng không đọc version bị chọn | Không biết BOM hoặc transitive dependency nào thắng | Dùng verbose tree và effective POM |
| Nâng Boot major nhưng giữ cấu hình cũ nguyên trạng | Có thể vướng Jakarta, starter hoặc API migration | Đọc migration guide/release notes của major |

## 15. Checklist trước khi bắt đầu một dự án WebFlux

- [ ] Xác định JDK tối thiểu và JDK thực tế trong production.
- [ ] Chọn Spring Boot release line phù hợp chính sách hỗ trợ.
- [ ] Kiểm tra System Requirements và migration guide.
- [ ] Dùng Boot parent/plugin và BOM cùng version.
- [ ] Khai báo `spring-boot-starter-webflux` không kèm version riêng.
- [ ] Chọn Reactor Netty mặc định hoặc xác định rõ Tomcat/Jetty.
- [ ] Tránh kéo MVC starter nếu ứng dụng phải là reactive server.
- [ ] Kiểm tra dependency tree cho Spring, Reactor, Reactor Netty và Netty.
- [ ] Kiểm tra không có version override/exclusion ngoài chủ đích.
- [ ] Build, test, startup và smoke test trên JDK/runtime gần production.
- [ ] Lưu dependency graph và kết quả test làm baseline cho lần nâng cấp tiếp theo.

## 16. Tự kiểm tra

**Câu 1.** Nếu dùng Spring Boot WebFlux, có cần khai báo version riêng cho reactor-core không?

**Thông thường không.** Boot BOM quản lý Reactor Core; hãy kiểm tra managed dependency coordinates của đúng release Boot.

**Câu 2.** Spring WebFlux có bắt buộc dùng Reactor Netty không?

**Không.** Spring Boot mặc định dùng Reactor Netty, nhưng Tomcat và Jetty cũng có thể chạy WebFlux thông qua adapter phù hợp.

**Câu 3.** Tại sao không nên lấy Spring Framework 7, Reactor mới nhất và Netty mới nhất ghép vào một ứng dụng Boot 3?

Vì từng bản Boot quản lý một bộ dependency đã được chọn tương thích. Ghép các version ngoài BOM có thể tạo lỗi binary, auto-configuration hoặc runtime.

**Câu 4.** `NoSuchMethodError` sau khi nâng dependency thường gợi ý điều gì?

Compiler và runtime có thể đang sử dụng **hai version khác nhau** của cùng class/artifact. Kiểm tra dependency tree, effective POM và nội dung jar được đóng gói.

**Câu 5.** Một ứng dụng dùng WebClient nhưng server vẫn là Spring MVC có thể có dependency WebFlux không?

Có. WebFlux cung cấp WebClient; việc thêm WebFlux để dùng client reactive không tự động đồng nghĩa server đang chạy WebFlux. Kiểm tra web application type.

**Câu 6.** Vì sao đổi Reactor Netty sang Tomcat cần chạy lại integration test?

Vì adapter HTTP, transport và cách server tích hợp khác nhau. Compile thành công không chứng minh network runtime mới hoạt động giống server cũ.

**Câu 7.** JDK developer là 21 nhưng Docker runtime là 17, có chắc chạy được không?

Không. Cần bảo đảm bytecode target và mọi dependency tương thích Java 17, sau đó test thực sự trên image runtime.

**Câu 8.** Nếu chỉ muốn cập nhật Netty do một security advisory, có nên sửa version một module duy nhất không?

Không nên làm tùy tiện. Đọc khuyến nghị của Boot/Reactor Netty, cập nhật bộ module tương thích và chạy test network/TLS phù hợp.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) — Java, Maven, Gradle và yêu cầu của đúng release Boot.
- [Spring Boot Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html) — version được Boot BOM quản lý, gồm Spring, Reactor, Reactor Netty và Netty.
- [Spring Boot Build Systems: Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — dùng dependency management với Maven và Gradle.
- [Spring Boot Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html) — WebFlux starter, application type và reactive server auto-configuration.
- [Spring Boot Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html) — dùng Reactor Netty, Tomcat hoặc Jetty và cách thay server starter.
- [Spring Framework WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html) — server APIs được hỗ trợ và kiến trúc adapter.
- [Project Reactor Documentation](https://projectreactor.io/docs) — Reactor Core, Reactor Test và release documentation.
- [Reactor Netty Reference Guide](https://projectreactor.io/docs/netty/release/reference/) — client/server, transport và cấu hình Reactor Netty.
- [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — xem dependency graph Maven.

**Ghi nhớ:** Hãy chọn **JDK và Spring Boot release line trước**, sau đó để **Boot BOM** đồng bộ Spring Framework, Reactor Core, Reactor Netty và Netty. WebFlux là framework; Reactor Netty, Tomcat và Jetty là những runtime server có thể lựa chọn. Kiểm tra version được resolve bằng effective POM/dependency tree, giữ server và JDK nhất quán với production, rồi xác nhận bằng build, startup và integration test trên đúng môi trường triển khai.