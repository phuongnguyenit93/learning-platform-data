# Ứng dụng không khởi động do starter, BOM hoặc web stack không tương thích

## 1. Vì sao Spring Cloud Gateway có thể không khởi động?

**Spring Cloud Gateway** là API Gateway của hệ sinh thái Spring: định tuyến request bằng **route predicate**, thực thi **GatewayFilter/GlobalFilter chain**, biến đổi path/header, khám phá dịch vụ, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request. Gateway chỉ có thể thực hiện các chức năng đó khi **starter, Spring Boot, Spring Cloud Release Train và web runtime** tạo thành một bộ dependency tương thích.

Những lỗi startup thường gặp không xuất phát từ route YAML hay backend, mà từ lớp nền:

- Dùng **Spring Boot 4.2** cùng Spring Cloud Release Train chỉ hỗ trợ Boot 4.0/4.1.
- Thêm BOM Spring Cloud nhưng quên thêm **Gateway starter**, nên dependency được quản lý version nhưng tính năng Gateway không có trên classpath.
- Copy starter cũ vào dự án Gateway Server phiên bản mới, trong khi tài liệu hiện hành dùng starter tách riêng cho **WebFlux** và **Web MVC**.
- Vô tình đưa cả Spring Boot Web và WebFlux vào cùng ứng dụng. Spring Boot mặc định chọn **Spring MVC** khi cả hai cùng xuất hiện, trong khi Gateway Server WebFlux cần **WebFlux + Reactor Netty**.
- Một dependency khác kéo Spring MVC, Tomcat, Reactor Netty hoặc Spring Framework phiên bản không cùng dòng; ứng dụng có thể fail ngay khi start hoặc ném lỗi liên kết lớp khi route đầu tiên chạy.
- Triển khai Gateway WebFlux thành **WAR** vào Servlet container như Tomcat bên ngoài, mặc dù WebFlux Gateway Server yêu cầu Netty runtime và không hỗ trợ kiểu triển khai đó.
- Đặt version trực tiếp cho từng module Spring Cloud/Spring Framework/Netty, vô tình ghi đè các phiên bản đã được release train BOM quản lý.

**Mục tiêu bài học:** tìm đúng lớp gây lỗi, chứng minh bằng dependency graph và điều kiện auto-configuration, chọn đúng release train/starter/web stack, sau đó sửa cấu hình Maven/Gradle tối thiểu và kiểm tra lại runtime classpath.

> **Phạm vi:** bài tập trung vào **Spring Cloud Gateway Server WebFlux** và đối chiếu **Server Web MVC**. Phiên bản tham chiếu được cập nhật theo các release chính thức đến **24/11/2026**. Không áp dụng bảng phiên bản cho các bản milestone/snapshot hoặc enterprise support ngoài phạm vi; luôn xác nhận với trang release train tương ứng trước khi nâng cấp.

## 2. Xác định đúng biến thể Gateway trước khi sửa dependency

Spring Cloud Gateway có các biến thể có mục tiêu khác nhau. Đừng bắt đầu bằng việc thêm hàng loạt starter để “thử xem có chạy không”.

| Biến thể | Starter hiện hành | Web runtime | Khi nào chọn |
|---|---|---|---|
| **Gateway Server WebFlux** | **spring-cloud-starter-gateway-server-webflux** | Spring WebFlux, Project Reactor, Reactor Netty | API Gateway reactive, streaming, WebSocket và filter chain WebFlux |
| **Gateway Server Web MVC** | **spring-cloud-starter-gateway-server-webmvc** | Spring WebMvc.fn, Servlet runtime như Tomcat/Jetty | Gateway theo mô hình Servlet/imperative |
| **Gateway Proxy Exchange** | Các starter Proxy Exchange riêng theo WebFlux/MVC | WebFlux hoặc MVC | Một ứng dụng web tự định nghĩa handler và dùng ProxyExchange để proxy; không phải full Server Gateway |

### 2.1. Gateway Server WebFlux

Tài liệu chính thức yêu cầu starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>
```

Gateway Server WebFlux được xây dựng trên **Spring Boot, Spring WebFlux và Project Reactor**; cần Netty runtime do Boot/WebFlux cung cấp. Tài liệu nêu rõ biến thể này **không chạy trong Servlet container truyền thống và không đóng gói thành WAR**.

### 2.2. Gateway Server Web MVC

Nếu ứng dụng chủ đích dùng Servlet/Tomcat/Jetty, starter đúng là:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
```

Gateway Server Web MVC được xây dựng trên **Spring Boot và Spring WebMvc.fn**, hoạt động với Servlet runtime như Tomcat/Jetty. Các thư viện reactive hoặc pattern chỉ có trong WebFlux không tự động áp dụng cho biến thể MVC.

### 2.3. Không thêm cả hai starter vào một ứng dụng để chữa lỗi

```text
Không nên:
  spring-cloud-starter-gateway-server-webflux
  spring-cloud-starter-gateway-server-webmvc

Chọn một:
  WebFlux Server -> Netty + WebFlux
  MVC Server    -> Servlet + WebMvc.fn
```

Đưa cả hai vào classpath có thể làm Boot phải chọn một application type và tạo ra tập auto-configuration không như mong muốn. Nếu thật sự cần hai Gateway với hai runtime, tách thành **hai ứng dụng/deployment** có dependency và cấu hình riêng.

## 3. Kiểm tra ma trận Spring Cloud ↔ Spring Boot

### 3.1. Chọn Release Train theo Spring Boot

Spring Cloud dùng **Release Train** để quản lý các module cùng một thế hệ. BOM spring-cloud-dependencies không phải version của Spring Boot và cũng không phải version của riêng Gateway.

| Spring Cloud Release Train | Spring Boot tương thích | Dòng Gateway đi kèm thường gặp | Ghi chú |
|---|---|---|---|
| **2026.0.x – Paddington** | **4.2.x** | Gateway 5.1.x | 2026.0.0 GA dựa trên Boot 4.2.0; Gateway module 5.1.0 |
| **2025.1.x – Oakwood** | 4.0.x; 4.1.x từ 2025.1.2 | Gateway 5.0.x | Không dùng bản train trước 2025.1.2 để giả định đã hỗ trợ mọi Boot 4.1.x |
| **2025.0.x – Northfields** | 3.5.x | Gateway 4.3.x | Dòng Boot 3.5 |
| **2024.0.x – Moorgate** | 3.4.x | Gateway 4.2.x | Dòng Boot 3.4 |
| **2023.0.x – Leyton** | 3.2.x; 3.3.x từ 2023.0.2 | Gateway 4.1.x | Dòng Boot 3.2/3.3 |
| **2022.0.x – Kilburn** | 3.0.x; 3.1.x từ 2022.0.3 | Gateway 4.0.x | Dòng cũ; kiểm tra trạng thái hỗ trợ trước khi duy trì |

**Đọc bảng đúng cách:**

- Bảng này giúp chọn **dòng tương thích**, không thay thế release notes/compatibility verifier của service release cụ thể.
- Patch version của Gateway được release train BOM quản lý. Ví dụ Spring Cloud 2026.0.0 chứa Gateway 5.1.0; không tự chọn một bản Gateway 5.1.x khác với BOM nếu không có lý do và kiểm thử.
- Spring Cloud 2025.1.2 trở lên mới mở rộng hỗ trợ Boot 4.1.x; mốc service release có ý nghĩa, không chỉ số 2025.1.
- **Tương thích không đồng nghĩa còn hỗ trợ OSS.** Các release train cũ có thể đã hết vòng đời; kiểm tra support status trước khi quyết định giữ bản cũ.
- Không ghép Boot 4.2 với Spring Cloud 2025.1 hoặc Boot 3.5 với Spring Cloud 2026.0 chỉ vì dependency resolver tìm được artifact trên Maven Central.

### 3.2. Cặp tham chiếu hiện hành tại ngày 24/11/2026

```text
Spring Boot 4.2.0
    + Spring Cloud 2026.0.0 (Paddington)
        + Spring Cloud Gateway 5.1.0

Spring Boot 4.0.x / 4.1.x
    + Spring Cloud 2025.1.x (Oakwood; 4.1.x từ 2025.1.2)
        + Spring Cloud Gateway 5.0.x

Spring Boot 3.5.x
    + Spring Cloud 2025.0.x (Northfields)
        + Spring Cloud Gateway 4.3.x
```

Đây là các cặp minh họa theo release train; dùng **latest service release còn được hỗ trợ** trong dòng đã chọn, không copy patch version từ ví dụ cũ. Trang Spring Cloud project và trang Spring Cloud Release là nguồn kiểm tra chính thức cho compatibility và module versions.

## 4. Starter đúng nhưng ứng dụng vẫn không có Gateway?

### 4.1. BOM chỉ quản lý version, không tự thêm dependency

Một lỗi rất thường gặp:

```xml
<!-- Chỉ import BOM: CHƯA có Gateway starter trên classpath -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2026.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

dependencyManagement chỉ **quản lý phiên bản** khi dependency được khai báo; nó không thêm các dependency đó vào runtime. Cần thêm starter trong dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
```

Nếu chỉ import BOM mà không có starter, ứng dụng Boot có thể khởi động như một app bình thường nhưng **không tạo Gateway Server**, không có route handler/filters như mong muốn.

### 4.2. Dùng artifact cũ trong tài liệu cũ

Một số hướng dẫn Gateway đời trước dùng:

```xml
<artifactId>spring-cloud-starter-gateway</artifactId>
```

Tài liệu hiện hành của Gateway Server tách starter rõ ràng:

- **spring-cloud-starter-gateway-server-webflux**
- **spring-cloud-starter-gateway-server-webmvc**

Đừng trộn một starter legacy với một BOM mới chỉ vì tên artifact có vẻ gần giống. Khi nâng cấp, đọc trang **How to Include** của đúng Gateway release; kiểm tra artifact tồn tại và version được BOM quản lý.

### 4.3. Nhầm starter với module core

Các tọa độ spring-cloud-gateway-server-webflux, spring-cloud-gateway-server-webmvc và các starter tương ứng không có vai trò giống nhau. Trong ứng dụng thông thường, dùng **starter được tài liệu hướng dẫn**, để nó kéo các module nền cần thiết. Không thay starter bằng một module core đơn lẻ rồi mong Boot tự cấu hình đầy đủ runtime.

## 5. Maven: cấu hình BOM đúng và dependency không khai version riêng

### 5.1. Ví dụ Maven chuẩn: Boot 4.2.0 + Cloud 2026.0.0

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>gateway</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
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
</project>
```

**Những điều quan trọng trong POM:**

1. spring-boot-starter-parent quản lý phiên bản Spring Boot/Spring Framework và plugin defaults.
2. spring-cloud-dependencies import **Release Train BOM** để quản lý Spring Cloud modules.
3. spring-cloud-starter-gateway-server-webflux **không có version riêng**; version đến từ BOM.
4. spring-boot-starter-actuator là dependency tùy nhu cầu quan sát; không bắt buộc để Gateway route hoạt động.
5. Không thêm spring-boot-starter-web vào ứng dụng WebFlux chỉ vì muốn dùng annotation controller. WebFlux cũng hỗ trợ annotation-based controllers.

Nếu dùng Spring Boot BOM thay vì Boot parent, vẫn cần import Boot BOM và Spring Cloud BOM theo một cấu trúc rõ ràng. **Không import nhiều BOM Spring khác nhau rồi thêm version thủ công cho các module nền** khi chưa biết thứ tự quản lý dependency.

### 5.2. Lỗi POM phổ biến

```xml
<!-- SAI: đặt version Gateway riêng, có thể lệch Release Train BOM -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    <version>5.0.5</version>
</dependency>

<!-- SAI: ép riêng Spring Framework không cùng Boot BOM -->
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
    <version>7.0.9</version>
</dependency>
```

Khi dùng BOM, tránh override thủ công:

- Spring Cloud Gateway/Commons/LoadBalancer modules.
- Spring Framework spring-core, spring-context, spring-webflux, spring-webmvc.
- Reactor reactor-core, reactor-netty.
- Netty modules.
- Spring Security modules.

Nếu cần một version patch khác để xử lý CVE hoặc workaround, phải kiểm tra **ma trận tương thích của toàn bộ dependency graph**, ghi rõ lý do và chạy integration tests. Không chỉ ép một artifact rồi hy vọng binary API tương thích.

### 5.3. BOM import order và explicit versions

Maven quản lý dependency theo effective POM và dependency mediation. Khi nhiều BOM cùng quản lý một artifact, thứ tự import/explicit dependency management có thể làm thay đổi version cuối cùng; version khai trực tiếp trên dependency cũng có thể override version do BOM đề xuất.

Quy tắc thực tế:

1. Chọn **một Boot parent/BOM** và **một Spring Cloud release train BOM**.
2. Đặt version train tại một property duy nhất, ví dụ spring-cloud.version.
3. Không import BOM của Spring Framework/Reactor/Netty khác trừ khi có tài liệu và lý do rõ.
4. Không đặt version trực tiếp trên starter Gateway.
5. Đọc **effective POM** và dependency tree thay vì đoán từ pom.xml nhìn thấy.

## 6. Gradle: import Release Train BOM một lần

### 6.1. Gradle Groovy DSL với dependency management plugin

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2026.0.0')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### 6.2. Các lỗi Gradle thường gặp

- Đặt version riêng trên Gateway starter dù đã import Spring Cloud BOM.
- Dùng resolutionStrategy.force để ép spring-webflux, spring-core, Reactor hoặc Netty.
- Version catalog (libs.versions.toml) giữ một version khác với BOM.
- Có nhiều platform/BOM import quản lý cùng dependency và không kiểm tra dependencyInsight.
- Gradle daemon chạy JDK khác với Java toolchain/compiler, khiến build qua nhưng bootRun hoặc container runtime fail.

Gradle có thể chọn version theo resolution strategy; kết quả cuối cần xem bằng dependencyInsight, không suy từ declaration ban đầu.

### 6.3. Gradle Kotlin DSL tương đương

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

extra["springCloudVersion"] = "2026.0.0"

dependencyManagement {
    imports {
        mavenBom(
            "org.springframework.cloud:spring-cloud-dependencies:" +
                property("springCloudVersion")
        )
    }
}

dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webflux")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Chọn **một** DSL (Groovy hoặc Kotlin) và một phương thức BOM management. Không copy cả hai vào cùng build.

## 7. Xung đột web stack: WebFlux bị Boot chọn thành Spring MVC

### 7.1. Quy tắc auto-detection của Spring Boot

Spring Boot nhận diện application type dựa trên classpath. Khi chỉ có WebFlux, Boot cấu hình reactive application. Khi cả Spring MVC và Spring WebFlux cùng có mặt, Boot mặc định chọn **Spring MVC**. Hành vi này tồn tại vì nhiều ứng dụng MVC thêm WebFlux chỉ để dùng reactive WebClient.

```text
spring-cloud-starter-gateway-server-webflux
    -> Spring WebFlux + Reactor Netty

spring-boot-starter-web
    -> Spring MVC + Servlet API + Tomcat (mặc định)

Cả hai cùng có mặt:
    -> Boot mặc định chọn Spring MVC
    -> Gateway Server WebFlux không có runtime phù hợp
```

### 7.2. Dependency nào thường kéo Spring MVC?

| Dependency/nhóm | Có thể kéo theo | Hướng xử lý khi dùng Gateway WebFlux |
|---|---|---|
| spring-boot-starter-web | Spring MVC, embedded Tomcat | Loại khỏi ứng dụng nếu không cần Servlet |
| spring-boot-starter-tomcat | Servlet container | Không dùng làm server cho Gateway WebFlux |
| spring-webmvc | Spring MVC APIs/auto-configuration | Tìm dependency nào kéo vào; không loại trừ mù quáng |
| spring-boot-starter-webflux | WebFlux, Reactor Netty server starter theo cấu hình | Thường đã được Gateway WebFlux starter kéo vào |
| spring-boot-starter-reactor-netty | Reactor Netty | Cần có runtime Netty cho Gateway WebFlux |
| spring-cloud-starter-gateway-server-webmvc | Gateway MVC/WebMvc.fn | Dùng khi chọn Servlet Gateway, không thêm cùng WebFlux Server |

Một dependency thư viện có thể kéo Spring MVC transitively dù POM của ứng dụng không khai báo trực tiếp. Vì vậy hãy đọc **runtime dependency tree**, không chỉ tìm trong phần dependencies trực tiếp.

### 7.3. Cách sửa đúng khi muốn Gateway WebFlux

Loại starter MVC/Servlet khỏi ứng dụng Gateway và giữ starter WebFlux:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Nếu một thư viện nội bộ kéo starter MVC, tìm dependency path bằng Maven/Gradle rồi **sửa module gây ra** hoặc exclude đúng dependency không cần. Không exclude toàn bộ Spring Framework/Servlet packages vì có thể làm hỏng một thư viện khác.

### 7.4. Có thể ép application type thành reactive không?

Spring Boot có property:

```yaml
spring:
  main:
    web-application-type: reactive
```

Property này có thể buộc Boot tạo reactive application context khi cả MVC và WebFlux cùng hiện diện. Nó hữu ích để **xác minh giả thuyết** trong một ứng dụng có lý do rõ ràng giữ cả hai API. Nhưng đối với Gateway Server WebFlux:

- Tài liệu Gateway yêu cầu Netty runtime.
- Một dependency Servlet còn trên classpath vẫn có thể mang theo auto-configuration, filters và beans không phù hợp.
- Deploy vào external Servlet container/WAR vẫn không trở thành WebFlux Gateway hợp lệ chỉ nhờ property.

**Sửa gốc:** loại dependency MVC/Servlet không cần và để Gateway WebFlux starter thiết lập runtime đúng. Chỉ giữ property ép reactive nếu kiến trúc đã được chủ đích thiết kế và integration tests chứng minh.

### 7.5. Nếu ứng dụng thực sự cần Servlet/Tomcat

Chọn Gateway Server Web MVC:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
```

Không thêm Gateway WebFlux starter chỉ để có thêm filter/reactive API. Kiểm tra lại các Gateway features, Java route/filter APIs và thư viện hỗ trợ của **Server Web MVC**; không phải mọi GatewayFilter WebFlux đều dùng nguyên trạng trong MVC.

## 8. Kiểm tra Java, Maven/Gradle và runtime thực tế

### 8.1. Build JDK và runtime JDK có thể khác nhau

Một project có thể compile bằng JDK mới nhưng container hoặc IDE lại chạy bằng JDK cũ. Hãy kiểm tra:

```bash
java -version
mvn -version
./mvnw -version
./gradlew -version
```

Các lệnh trên cho biết JVM của shell, Maven và Gradle daemon. Nếu dùng toolchain, kiểm tra toolchain được chọn trong build log và runtime image/container.

### 8.2. Lỗi class version

Nếu log có:

```text
UnsupportedClassVersionError
class file version XX.0
runtime only recognizes up to YY.0
```

Class đã được compile bằng Java mới hơn runtime đang chạy. Kiểm tra:

1. Java toolchain trong Maven/Gradle.
2. JAVA_HOME của CI, IDE, shell và container.
3. Image JRE trong Dockerfile.
4. Maven compiler release/source/target nếu có override.
5. Build cache chứa artifact được compile từ JDK khác.

Đừng chỉ thay JAVA_HOME trên một terminal rồi quên cấu hình JDK của IDE/Gradle daemon.

### 8.3. Không nhầm Java version với Spring version

| Dấu hiệu | Cần kiểm tra |
|---|---|
| UnsupportedClassVersionError | Java runtime thấp hơn bytecode |
| NoSuchMethodError trong Spring | Spring Framework modules lệch version |
| NoClassDefFoundError Reactor/Netty | Runtime dependency thiếu hoặc bị exclude |
| Spring Cloud compatibility verifier fail | Boot và Spring Cloud Release Train không tương thích |
| Build tool không nhận plugin | Maven/Gradle wrapper, plugin version và JDK của build tool |

Java 21 trong các POM mẫu là một lựa chọn toolchain minh họa; chọn Java version nằm trong yêu cầu của Spring Boot release bạn dùng và thống nhất trên CI/runtime.

## 9. Đọc đúng lỗi startup và ánh xạ tới nguyên nhân

| Dấu hiệu trong log | Nguyên nhân thường gặp | Bước kiểm tra |
|---|---|---|
| Spring Cloud compatibility verifier báo Boot version không tương thích | Chọn sai Release Train BOM | Đối chiếu Boot ↔ Cloud matrix, không tắt verifier để che lỗi |
| NoSuchMethodError trong org.springframework.* | Spring Framework modules không cùng dòng | Maven dependency tree/Gradle dependencyInsight; tìm version override |
| NoClassDefFoundError cho org.springframework.web.reactive.* | WebFlux bị thiếu hoặc bị exclude | Kiểm tra Gateway starter và runtimeClasspath |
| NoClassDefFoundError cho reactor.netty.http.server.HttpServer | Reactor Netty server runtime bị thiếu/loại | Kiểm tra starter WebFlux, dependency exclusions và jar packaging |
| Boot khởi tạo ServletWebServerApplicationContext thay vì reactive | spring-boot-starter-web/spring-webmvc còn trên classpath | Tìm dependency kéo MVC; chọn đúng Gateway flavor |
| Không tìm thấy ServletWebServerFactory khi ép Servlet | Application type là SERVLET nhưng không có Servlet server phù hợp | Chọn MVC starter/runtime hoặc bỏ ép application type |
| Gateway không xuất hiện nhưng app khởi động bình thường | Chỉ import BOM, chưa khai Gateway starter | Thêm đúng starter trong dependencies |
| Could not resolve artifact | Sai group/artifact/version/repository hoặc dùng milestone không có repo | Kiểm tra tọa độ, Maven Central/repository và release docs |
| BeanDefinitionOverrideException | Starter/auto-config trùng hoặc bean tự định nghĩa xung đột | Tìm bean name và nguồn config; không bật override toàn cục ngay |
| NoSuchBeanDefinitionException cho reactive server/handler | Web stack hoặc auto-configuration không chạy | Kiểm tra application type và condition report |
| NoSuchMethodError chỉ xuất hiện khi request đầu tiên | Lệch binary version trong code path chưa được load lúc startup | Dependency graph + smoke test route thật |
| App chạy trong IDE nhưng fail trong jar | Runtime packaging/classpath khác IDE | Kiểm tra BOOT-INF/lib trong executable jar và lệnh java -jar |
| App chạy local nhưng fail trong container | JDK/base image, profile, env hoặc dependency packaging khác | So sánh runtime Java, active profiles và image artifact |

**Nguyên tắc:** giữ nguyên **exception đầu tiên có ý nghĩa** và stack trace gốc. Các lỗi phía sau thường chỉ là hậu quả khi Spring context đã fail. Đừng bắt đầu sửa bean cuối cùng trong stack nếu nguyên nhân thực tế là version mismatch ở đầu log.

## 10. Quy trình chẩn đoán dependency graph

### 10.1. Maven: xem effective POM và dependency tree

Chạy trong thư mục có Maven wrapper/POM:

```bash
./mvnw -version

# POM sau khi hợp nhất parent, properties và imported BOMs.
./mvnw help:effective-pom -Doutput=target/effective-pom.xml

# Toàn bộ cây dependency runtime/compile, gồm cả đường kéo transitively.
./mvnw dependency:tree -Dverbose

# Lọc nhóm Spring Cloud/Spring Boot nếu cần.
./mvnw dependency:tree -Dverbose \
  -Dincludes=org.springframework.cloud:*,org.springframework.boot:*

# Tìm các module web stack và Reactor/Netty.
./mvnw dependency:tree -Dverbose \
  -Dincludes=org.springframework:*,io.projectreactor:*,io.netty:*
```

**Cần nhìn gì trong output?**

- Có đúng Gateway starter không?
- Có hơn một phiên bản Spring Cloud Gateway/Commons/LoadBalancer không?
- Spring Boot artifacts có cùng version line không?
- Spring Framework artifacts có cùng version line không?
- Có cả spring-webmvc và spring-webflux không?
- Có reactor-netty-http và server runtime tương ứng không?
- Dependency nào kéo Tomcat/Servlet/MVC vào?
- Có dependency bị đánh dấu omitted for conflict với version không mong muốn không?

File effective POM là bằng chứng cho **dependencyManagement cuối cùng**. Nếu version starter trong POM không có version nhưng dependency tree ra một version lạ, tìm parent/BOM/property đã quản lý nó.

### 10.2. Gradle: dùng dependencies và dependencyInsight

```bash
./gradlew -version

# Toàn bộ runtime classpath.
./gradlew dependencies --configuration runtimeClasspath

# Ai kéo Gateway WebFlux starter và version nào được chọn?
./gradlew dependencyInsight \
  --dependency spring-cloud-starter-gateway-server-webflux \
  --configuration runtimeClasspath

# Tìm nguồn kéo Spring MVC.
./gradlew dependencyInsight \
  --dependency spring-webmvc \
  --configuration runtimeClasspath

# Tìm nguồn kéo Servlet/Tomcat.
./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath

# Kiểm tra Reactor Netty.
./gradlew dependencyInsight \
  --dependency reactor-netty-http \
  --configuration runtimeClasspath
```

Gradle dependencyInsight cho biết **selected version**, các candidate versions và dependency path. Hãy xử lý dependency path kéo version xung đột; tránh thêm resolutionStrategy.force trước khi hiểu nguyên nhân.

### 10.3. Kiểm tra executable jar

Khi ứng dụng chạy trong IDE nhưng không chạy từ jar:

```bash
jar tf target/gateway.jar | grep 'BOOT-INF/lib'

# Lọc các module web/runtime cần kiểm tra.
jar tf target/gateway.jar | grep -E \
  'BOOT-INF/lib/(spring-cloud-gateway|spring-boot-starter-web|spring-boot-starter-webflux|spring-webmvc|spring-webflux|reactor-netty|tomcat)'
```

Nếu dùng PowerShell, có thể thay grep bằng Select-String. Với Boot executable jar, dependencies nằm trong BOOT-INF/lib. Đối chiếu jar thực tế được deploy, không chỉ xem dependency tree của IDE.

### 10.4. Route chưa phải bước đầu tiên

Nếu ứng dụng chưa tạo được ApplicationContext hoặc web server, route predicates, filters, backend DNS và TLS upstream **chưa phải nơi điều tra đầu tiên**. Trình tự nên là:

1. Build tool/JDK.
2. BOM/release train.
3. Starter/coordinate.
4. Web application type/runtime.
5. Auto-configuration/context startup.
6. Sau khi app start: route definitions, filters, upstream connection.

## 11. Dùng Condition Evaluation Report để tìm auto-configuration bị bỏ qua

### 11.1. Bật debug lúc chạy

```bash
# Maven Spring Boot plugin
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug

# Gradle
./gradlew bootRun --args='--debug'

# Executable jar
java -jar target/gateway.jar --debug
```

Spring Boot in **Condition Evaluation Report** để giải thích auto-configuration nào match hoặc không match. Tìm các mục liên quan:

- Gateway Server WebFlux auto-configuration.
- WebFlux/Reactive web server auto-configuration.
- Servlet/MVC auto-configuration.
- Reactor Netty server factory.
- Các condition theo classpath và application type.

### 11.2. Cách đọc report

| Report cho thấy | Cách hiểu |
|---|---|
| Gateway WebFlux auto-config không match vì class missing | Starter/module nền chưa có hoặc bị exclude |
| Gateway WebFlux auto-config không match vì web application type | Boot đang chạy SERVLET/NONE thay vì REACTIVE |
| Servlet auto-config match trong ứng dụng dự kiến WebFlux | Có thể spring-webmvc/starter-web đang trên classpath |
| Reactive server factory không có | Kiểm tra Reactor Netty starter/runtime và exclusions |
| Gateway auto-config match nhưng route list rỗng | Starter có mặt; chuyển sang kiểm tra route configuration/profile |

**Không bật tất cả Actuator endpoints chỉ để đọc condition report.** Debug log lúc startup là đủ trong nhiều trường hợp; nếu dùng Actuator conditions endpoint thì bảo vệ quyền truy cập và không expose công khai.

### 11.3. Kiểm tra application type bằng cấu hình

Có thể ghi tạm:

```yaml
spring:
  main:
    web-application-type: reactive
```

Nếu application bắt đầu chạy khi ép reactive, đây là bằng chứng mạnh cho thấy **web stack detection/classpath** đang sai. Sau đó quay lại dependency tree và loại dependency Servlet không cần; đừng giữ override chỉ để che xung đột mà chưa kiểm tra Netty/runtime.

## 12. Minimal application và smoke test sau khi sửa

### 12.1. Main class tối thiểu

Gateway Server WebFlux không cần một annotation đặc biệt để “bật Gateway”; starter và auto-configuration đảm nhiệm phần này:

```java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

Tránh thêm một cách tùy tiện:

```java
@EnableWebMvc
@SpringBootApplication
public class GatewayApplication {
    // Không phù hợp với Gateway Server WebFlux.
}
```

@EnableWebMvc yêu cầu cấu hình Spring MVC. Trong một ứng dụng WebFlux Gateway, annotation này có thể làm web stack không còn đúng như dự kiến. @EnableWebFlux cũng chuyển quyền cấu hình WebFlux về ứng dụng và có thể làm mất một số auto-configuration mặc định của Boot. Chỉ dùng khi thực sự muốn tự quản lý toàn bộ cấu hình web và đã hiểu tác động.

### 12.2. Route smoke test tối thiểu

Sau khi context khởi động được, thêm một route test tới backend giả định:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: startup-smoke
              uri: http://localhost:8081
              predicates:
                - Path=/smoke/**
              filters:
                - StripPrefix=1
```

Route này chỉ là **smoke test sau startup**, không cần backend chạy để tạo ApplicationContext. Khi gửi request, nếu backend chưa chạy thì có thể nhận 502/503/connection refused; điều đó là lỗi upstream, không phải lỗi BOM/starter nữa.

### 12.3. Test chỉ xác minh Spring context có thể khởi động

```java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayApplicationStartupTest {

    @Test
    void applicationContextStarts() {
        // Test pass khi context và reactive server khởi động thành công.
    }
}
```

Test này phát hiện nhiều lỗi starter/web stack/BOM trước khi deploy. Tuy nhiên, nó chưa chứng minh route thực sự proxy được hoặc dependency lazy-loaded không lỗi; cần thêm một integration smoke test gọi route sau khi backend stub đã sẵn sàng.

### 12.4. Chạy lại sau khi sửa dependency

```bash
# Maven: kiểm tra compile/test/package từ trạng thái sạch.
./mvnw clean verify

# Gradle: kiểm tra compile/test.
./gradlew clean test

# Chạy app với debug report trong sandbox.
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Không xóa toàn bộ Maven/Gradle cache theo phản xạ. Chỉ dùng refresh/update dependencies khi có bằng chứng cache/repository metadata bị stale; nếu dependency graph vẫn sai, tải lại cache sẽ không sửa được version conflict.

## 13. Các lỗi startup điển hình và cách xử lý từng bước

### 13.1. Compatibility verifier báo Spring Boot không tương thích

Ví dụ log có nội dung tương tự:

```text
Spring Boot [4.2.0] is not compatible with this Spring Cloud release train
```

Nguyên nhân: Spring Cloud BOM đang dùng không hỗ trợ dòng Boot đó.

**Cách sửa:**

1. Ghi lại chính xác Boot version trong effective POM/Gradle runtimeClasspath.
2. Xác định Spring Cloud release train BOM đang được import thực tế.
3. Đối chiếu compatibility matrix và service release.
4. Chọn một cặp tương thích, ví dụ Boot 4.2.x + Cloud 2026.0.x hoặc Boot 4.0/4.1 + Cloud 2025.1.x theo mốc hỗ trợ.
5. Để BOM quản lý Gateway/Commons/LoadBalancer modules, không ép riêng version.
6. Chạy clean verify và smoke test.

Không tắt compatibility verifier bằng:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: false
```

Property này có thể bỏ qua cảnh báo/kiểm tra tương thích nhưng **không biến các binary API không tương thích thành tương thích**. Chỉ dùng khi Spring support team hoặc release notes yêu cầu một ngoại lệ có kiểm soát, và phải có kiểm thử đầy đủ.

### 13.2. NoSuchMethodError hoặc AbstractMethodError

Ví dụ:

```text
java.lang.NoSuchMethodError:
  org.springframework.web.server.ServerWebExchange.someMethod(...)

java.lang.AbstractMethodError:
  Receiver class ... does not define ...
```

Đây thường là dấu hiệu code được compile với một API nhưng runtime nạp một version khác. Các nguyên nhân:

- Boot parent/BOM và Cloud BOM không cùng thế hệ.
- Một starter được khai version trực tiếp.
- Một library transitively kéo Spring Framework/Reactor/Netty version khác.
- Gradle force/constraint/version catalog ghi đè BOM.
- Fat jar chứa dependency khác với dependency tree trong IDE.

**Cách xử lý:** tìm artifact sở hữu class trong stack trace, chạy dependency tree/dependencyInsight, xác định đường dependency kéo version đang được nạp, rồi loại override hoặc nâng/downgrade dependency ở đúng tầng. Không sửa bằng cách thêm một dependency cùng class với version mới vào cuối POM.

### 13.3. NoClassDefFoundError cho WebFlux hoặc Reactor Netty

Ví dụ:

```text
java.lang.NoClassDefFoundError: org/springframework/web/reactive/...
java.lang.NoClassDefFoundError: reactor/netty/http/server/HttpServer
```

Kiểm tra:

1. Đúng starter Gateway Server WebFlux đã được khai báo trong dependencies.
2. Dependency có scope runtime/compile phù hợp, không chỉ test scope.
3. Không có exclusion vô tình loại Spring WebFlux hoặc Reactor Netty.
4. Jar đóng gói thực sự chứa module cần thiết trong BOOT-INF/lib.
5. Không deploy ứng dụng WebFlux Gateway như WAR trong Servlet container.

Nếu cần WebClient trong một ứng dụng MVC, việc thêm WebFlux client libraries không đồng nghĩa ứng dụng đã trở thành WebFlux Gateway. Hãy phân biệt **client library** với **reactive server runtime**.

### 13.4. Boot chọn Servlet application context

Triệu chứng:

- Log cho thấy Servlet web server/application context.
- Ứng dụng cố khởi tạo Tomcat/Servlet container.
- Gateway WebFlux auto-configuration không match theo application type.

**Cách sửa:**

1. Chạy dependencyInsight cho spring-webmvc và spring-boot-starter-web.
2. Tìm dependency trực tiếp hoặc transitively kéo MVC/Tomcat.
3. Nếu không cần MVC, loại starter/dependency đó.
4. Giữ Gateway Server WebFlux starter và Reactor Netty.
5. Chỉ dùng spring.main.web-application-type=reactive như công cụ chẩn đoán hoặc cấu hình có chủ đích, không thay cho việc làm sạch dependency graph.

### 13.5. Không tìm thấy embedded server factory

Nếu log nói không có reactive server factory hoặc không tạo được Netty server:

- Kiểm tra Reactor Netty server dependency có trong runtime classpath.
- Kiểm tra có exclude spring-boot-starter-reactor-netty hay không.
- Kiểm tra custom server starter có thay thế server mặc định hay không.
- Kiểm tra profile/container build có đóng gói thiếu thư viện.
- Đối chiếu version Boot/Reactor Netty theo BOM.

Không thêm Tomcat starter để “có một server nào đó” nếu mục tiêu là Gateway WebFlux; Gateway yêu cầu Netty runtime.

### 13.6. App khởi động nhưng không có Gateway routes

Đây không nhất thiết là lỗi web stack. Kiểm tra:

1. Starter đã có trong runtime classpath hay mới chỉ có BOM?
2. Route config có đúng prefix theo Gateway release không?
3. Profile đang active có chứa routes không?
4. Gateway có bị disable bằng property không?
5. Route definitions có được load từ Config Server/discovery source không?

Ở các release mới, prefix Server WebFlux thường bắt đầu bằng spring.cloud.gateway.server.webflux; các dòng cũ có thể dùng spring.cloud.gateway. Đọc configuration properties của **đúng version**, không trộn YAML 4.x và 5.x.

## 14. Runbook chẩn đoán từ lỗi đầu tiên tới bản sửa

### 14.1. Thu thập bằng chứng tối thiểu

Trước khi thay dependency, ghi lại:

- Spring Boot version thực tế.
- Spring Cloud Release Train BOM thực tế.
- Spring Cloud Gateway module version được chọn.
- JDK của Maven/Gradle và JDK runtime.
- Web application type: reactive hay servlet.
- Runtime server: Reactor Netty hay Tomcat/Jetty.
- Stack trace đầu tiên và Condition Evaluation Report.
- Build tool và profile active.

Không cần gửi toàn bộ environment variables hoặc secrets vào ticket. Redact credentials/URLs chứa token và private hostnames khi chia sẻ logs.

### 14.2. Trình tự thao tác

```text
1. Xác định ý định:
   WebFlux Gateway hay MVC Gateway?

2. Kiểm tra compatibility:
   Spring Boot -> Spring Cloud release train -> Gateway module.

3. Kiểm tra starter:
   đúng artifact? có trong runtimeClasspath? BOM chỉ quản version?

4. Kiểm tra web stack:
   WebFlux + Netty? hay MVC + Servlet?
   Có spring-webmvc/Tomcat không mong muốn?

5. Kiểm tra version mediation:
   effective-pom / dependencyInsight / dependency tree.

6. Kiểm tra runtime artifact:
   executable jar có đúng libs? JDK đúng?

7. Sửa một nguyên nhân tại một thời điểm:
   không force hàng loạt versions.

8. Chạy clean verify + context startup test.

9. Chạy route smoke test với backend stub.

10. Ghi lại cặp versions và dependency policy đã xác nhận.
```

### 14.3. Ví dụ trước và sau

**Trước — Boot 4.2 + Cloud 2025.1 + cả hai web stacks:**

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
</parent>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    <version>5.0.5</version>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Vấn đề: Boot 4.2 cần Cloud 2026.0.x; starter 5.0.5 bị ép version và thuộc dòng Gateway khác; starter MVC/Servlet được thêm ngoài ý muốn.

**Sau — Boot 4.2 + Cloud 2026.0 + WebFlux Gateway:**

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
```

Kết quả mong đợi: Cloud BOM quản Gateway 5.1.x phù hợp; Boot nhận reactive stack; Netty server khởi động. Sau đó vẫn cần kiểm tra runtime tree và smoke test, không chỉ tin vào POM.

## 15. Các bẫy khi nâng cấp từ dự án Gateway cũ

### 15.1. Chỉ đổi Spring Boot version nhưng giữ nguyên Spring Cloud BOM

Spring Boot và Spring Cloud có release train tương ứng. Nâng Boot major/minor mà không nâng Cloud BOM phù hợp có thể gây:

- Compatibility verifier fail ngay khi start.
- Spring Framework binary API mismatch.
- Auto-configuration condition thay đổi.
- Starter/artifact hoặc package migration.

Hãy nâng theo cặp release train và đọc release notes cho **tất cả modules Spring Cloud** đang dùng, không chỉ Gateway.

### 15.2. Copy starter từ tutorial cũ

Tutorial cũ có thể dùng spring-cloud-starter-gateway. Tài liệu Gateway Server mới dùng starter WebFlux/Web MVC riêng. Không trộn dependency cũ với properties/prefix mới.

### 15.3. Giữ spring-boot-starter-web chỉ để dùng controller

Spring WebFlux cũng hỗ trợ annotation controllers (RestController, GetMapping) và functional endpoints. Không cần thêm MVC starter chỉ để viết controller.

Nếu service thực sự cần mô hình Servlet, cân nhắc chuyển toàn Gateway sang **Server Web MVC** hoặc tách API application khỏi Gateway deployment. Không ép một runtime lai nếu không có lý do.

### 15.4. Dùng WebFlux Gateway như WAR

Gateway Server WebFlux cần Netty runtime và không chạy trong traditional Servlet container/WAR. Nếu tổ chức bắt buộc deploy WAR trên Tomcat/Jetty, chọn Server Web MVC hoặc một kiến trúc proxy khác phù hợp.

### 15.5. Tự pin Reactor/Netty vì thấy một lỗi runtime

Spring Cloud Gateway WebFlux dựa vào Spring Boot, Spring Framework, Reactor và Netty. Pin riêng một module có thể tạo một binary mixture khó chẩn đoán. Hãy tìm version conflict bằng dependency graph trước, sau đó chỉ override khi release notes/support chỉ rõ version và phạm vi.

## 16. Checklist CI để ngăn lỗi tái xuất hiện

- [ ] Chỉ có **một** Gateway Server flavor trong runtime classpath.
- [ ] Boot version nằm trong compatibility matrix của Spring Cloud Release Train.
- [ ] Gateway starter đúng flavor và không có version override riêng.
- [ ] BOM import đúng một release train, không trộn BOM Spring khác tùy tiện.
- [ ] Không có Spring MVC/Tomcat ngoài ý muốn trong WebFlux Gateway.
- [ ] Reactor Netty runtime có mặt khi dùng Gateway Server WebFlux.
- [ ] Java toolchain, Maven/Gradle daemon và runtime image dùng JDK tương thích.
- [ ] Dependency tree/dependencyInsight được kiểm tra khi nâng major/minor.
- [ ] Effective POM được lưu trong artifact CI khi cần audit.
- [ ] Executable jar chứa đúng runtime dependencies.
- [ ] Context startup test chạy trong CI.
- [ ] Route smoke test xác nhận proxy hoạt động sau khi context start.
- [ ] Không tắt compatibility verifier chỉ để pipeline xanh.
- [ ] Có kiểm tra riêng cho Docker/production image, không chỉ IDE classpath.

## 17. Bảng triệu chứng và hướng sửa nhanh

| Triệu chứng | Kiểm tra đầu tiên | Hướng sửa |
|---|---|---|
| Compatibility verifier fail | Boot version + Cloud BOM | Chọn release train tương thích |
| Không có Gateway routes | Runtime tree có Gateway starter? | Thêm đúng starter, kiểm tra property prefix/profile |
| Boot chọn Servlet | spring-webmvc/Tomcat có trong runtime? | Loại MVC dependency hoặc chọn Gateway MVC |
| Không có Netty server | reactor-netty-http có mặt? | Sửa starter/exclusion và runtime packaging |
| NoSuchMethodError | Spring Framework/Reactor version nào được nạp? | Đồng bộ BOM, bỏ version override |
| NoClassDefFoundError | Module bị exclude hay scope sai? | Khôi phục dependency runtime phù hợp |
| BeanDefinitionOverrideException | Starter/auto-config/bean trùng? | Chọn một flavor, xử lý bean conflict cụ thể |
| UnsupportedClassVersionError | JDK build so với JDK runtime | Đồng bộ toolchain và container JRE |
| Chạy IDE, fail java -jar | BOOT-INF/lib và active profile | Kiểm tra packaged jar/runtime config |
| Chạy local, fail container | JDK/image/env/profiles | So sánh môi trường chạy thực |
| Build pass, request đầu fail | Lazy linkage/classpath conflict | Dependency tree + route integration test |
| Gateway MVC chạy nhưng WebFlux filters không có | Nhầm hai server flavors | Dùng API/filter đúng biến thể |

## 18. Câu hỏi tự luyện và đáp án

**Bài 1 — BOM có tự thêm Gateway không?** Import spring-cloud-dependencies nhưng không khai starter. Ứng dụng có Gateway Server không?

**Đáp án:** không. BOM chỉ quản lý version; cần khai Gateway starter trong dependencies.

**Bài 2 — Boot 4.2.0 dùng Cloud train nào?**

**Đáp án:** Spring Cloud 2026.0.x (Paddington); 2026.0.0 GA dựa trên Boot 4.2.0.

**Bài 3 — Boot 4.1.x có thể dùng Cloud 2025.1.x từ bản nào?**

**Đáp án:** từ Spring Cloud 2025.1.2 trở lên theo compatibility notice của release train.

**Bài 4 — Hai starter WebFlux và Web MVC có thay thế trực tiếp cho nhau không?**

**Đáp án:** không. WebFlux dùng Netty/WebFlux/Project Reactor; MVC dùng WebMvc.fn và Servlet runtime.

**Bài 5 — Gateway WebFlux có chạy trong WAR trên Tomcat truyền thống không?**

**Đáp án:** không. Tài liệu Gateway Server WebFlux yêu cầu Netty runtime và không hỗ trợ traditional Servlet container/WAR.

**Bài 6 — Có cả spring-boot-starter-web và spring-boot-starter-webflux. Boot chọn gì mặc định?**

**Đáp án:** Spring Boot mặc định auto-configure Spring MVC khi cả hai cùng có mặt. Điều này xung đột với ý định chạy Gateway Server WebFlux.

**Bài 7 — Có thể đặt spring.main.web-application-type=reactive để sửa mọi xung đột không?**

**Đáp án:** không. Nó có thể ép application type nhưng không loại dependency Servlet, không sửa BOM mismatch và không bảo đảm Netty runtime đúng. Sửa dependency graph là cách ưu tiên.

**Bài 8 — NoSuchMethodError thường gợi ý điều gì?**

**Đáp án:** code/runtime binary version mismatch; xem dependency tree và effective POM thay vì thêm một dependency cùng class tùy tiện.

**Bài 9 — Gateway starter có cần khai version khi đã import Spring Cloud BOM?**

**Đáp án:** thông thường không. Để BOM quản lý version của starter và module Spring Cloud.

**Bài 10 — Vì sao build thành công nhưng app vẫn fail khi chạy?**

**Đáp án:** compile classpath có thể khác runtime classpath; có lazy linkage, thiếu Netty runtime, dependency exclusions, packaged jar khác IDE hoặc JDK runtime thấp hơn.

**Bài 11 — Khi nào dùng Gateway Server Web MVC?**

**Đáp án:** khi kiến trúc chủ đích dùng Servlet runtime/Tomcat/Jetty và WebMvc.fn; không phải cách chữa lỗi cho WebFlux Gateway đang cấu hình sai.

**Bài 12 — Có nên tắt compatibility verifier để khởi động được không?**

**Đáp án:** không nên. Verifier đang cảnh báo version mismatch; tắt nó không sửa binary incompatibility. Chọn đúng release train.

**Bài 13 — Dependency tree có spring-webmvc nhưng POM không khai báo trực tiếp. Điều gì cần làm?**

**Đáp án:** dùng Maven dependency:tree hoặc Gradle dependencyInsight để tìm module kéo Spring MVC vào, rồi sửa dependency path cụ thể.

**Bài 14 — Chỉ có actuator và cloud BOM nhưng không có Gateway starter. Điều gì xảy ra?**

**Đáp án:** Boot có thể khởi động một web application khác, nhưng không có Gateway Server auto-configuration/runtime như mong đợi.

**Bài 15 — Tại sao phải test executable jar sau khi IDE context start pass?**

**Đáp án:** jar đóng gói có thể thiếu, thêm hoặc đổi dependency so với IDE classpath; container JDK/profile cũng có thể khác.

**Bài 16 — Spring Boot 3.5.x nên đi với Cloud train nào trong bảng tham chiếu?**

**Đáp án:** Spring Cloud 2025.0.x (Northfields), với Gateway 4.3.x theo release train.

**Bài 17 — Dự án cũ dùng spring-cloud-starter-gateway. Có nên copy nguyên artifact đó sang Gateway 5.x?**

**Đáp án:** không. Đọc trang How to Include của đúng release và chọn starter Server WebFlux hoặc Server Web MVC tương ứng.

**Bài 18 — Context startup test pass có chứng minh route upstream hoạt động không?**

**Đáp án:** không. Cần integration smoke test gọi route và xác minh backend stub nhận request.

## 19. Tài liệu tham khảo chính thức

- [Spring Cloud Project – Release Train / Spring Boot compatibility](https://spring.io/projects/spring-cloud/): ma trận Boot ↔ Cloud và hướng dẫn chọn BOM.
- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/): Boot 4.2.0, Gateway 5.1.0 và Maven/Gradle BOM examples.
- [Spring Cloud Release 2026.0.0 reference](https://docs.spring.io/spring-cloud-release/reference/index.html): supported Boot version và module versions của release train.
- [Spring Cloud Gateway Server WebFlux – How to Include](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html): starter coordinate, WebFlux/Netty runtime và giới hạn Servlet/WAR.
- [Spring Cloud Gateway Server Web MVC – How to Include](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/starter.html): MVC starter, WebMvc.fn và Servlet runtime.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): hành vi khi cả starter MVC và WebFlux cùng có trên classpath.
- [Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem cây dependency và version mediation.
- [Gradle – Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies và dependencyInsight.
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java baseline theo Spring Boot release.

**Ghi nhớ:** Khi Gateway không khởi động, hãy xác định **đúng biến thể**, chọn **Spring Cloud Release Train tương thích với Spring Boot**, dùng **đúng starter**, và để BOM quản lý các module nền. Với Gateway Server WebFlux, phải có **WebFlux + Reactor Netty**, không để Spring MVC/Servlet runtime vô tình chiếm application type và không deploy WAR. Dependency tree, effective POM, dependencyInsight và Condition Evaluation Report là bằng chứng để sửa đúng nguyên nhân; sau đó chạy cả context startup test lẫn route smoke test trước khi phát hành.
