# Đối chiếu ma trận Spring Boot, Spring Cloud và Gateway trước nâng cấp

## 1. Vì sao phải đối chiếu ba phiên bản cùng lúc?

Một dự án **Spring Cloud Gateway** không chỉ có một phiên bản framework. Khi nâng cấp, ít nhất ba trục cần tương thích:

1. **Spring Boot** quản lý nền tảng ứng dụng, auto-configuration, runtime, dependency versions và plugin build.
2. **Spring Cloud Release Train** là BOM tập hợp các phiên bản tương thích của Spring Cloud Commons, LoadBalancer, CircuitBreaker, Gateway, Discovery integrations và các dự án liên quan.
3. **Spring Cloud Gateway** là một project nằm trong release train, có version riêng. Gateway WebFlux, Gateway Web MVC và Proxy Exchange còn có starter/API/runtime khác nhau.

Ví dụ, một ứng dụng đang chạy Spring Boot 3.5.x và Spring Cloud Gateway 4.3.x không thể chỉ đổi Boot lên 4.2.x rồi giữ nguyên Gateway 4.3.x theo thói quen. Tổ hợp mới phải chuyển sang release train hỗ trợ Boot 4.2.x và Gateway tương ứng. Nếu chọn sai, lỗi có thể xuất hiện khi resolve dependency, lúc Spring khởi động, hoặc chỉ khi request đi qua một filter cụ thể.

Bài này giúp bạn:

- Đọc đúng ma trận **Spring Boot ↔ Spring Cloud Release Train ↔ Spring Cloud Gateway**.
- Phân biệt tương thích kỹ thuật với vòng đời hỗ trợ OSS/Enterprise.
- Chọn BOM và starter đúng cách cho Maven/Gradle.
- Nhận diện thay đổi quan trọng khi chuyển Gateway 4.x → 5.x và Boot 3.5 → 4.x.
- Lập kế hoạch nâng cấp theo từng giai đoạn, có kiểm thử và rollback.
- Kiểm soát rủi ro Gateway: route/filter order, WebFlux/Web MVC, service discovery, forwarded headers, TLS, retry, circuit breaker, response cache và WebSocket.

> **Mốc dữ liệu trong bài: 24/11/2026.** Spring Cloud 2026.0.0 vừa được công bố GA ngày 20/11/2026; Spring Boot 4.2.0 được phát hành ngày 19/11/2026. Phiên bản ổn định và chính sách hỗ trợ có thể thay đổi sau mốc này. Trước khi nâng cấp production, hãy kiểm tra Spring Projects, release notes và security advisories mới nhất.

## 2. Hiểu ba trục phiên bản

### 2.1. Spring Boot version

Spring Boot version quyết định nền tảng runtime và bộ dependency do Boot quản lý. Các thành phần ảnh hưởng trực tiếp tới Gateway gồm:

- Spring Framework và Spring Security.
- Spring WebFlux/Reactor Netty hoặc Spring Web MVC/Servlet container.
- Jackson và HTTP message codecs.
- Micrometer, Actuator, Observation/Tracing.
- Embedded server, TLS/SSL, logging và configuration binding.

Boot major/minor upgrade có thể đổi package, starter, property hoặc behavior auto-configuration. Vì vậy, chỉ xem Gateway version là chưa đủ.

### 2.2. Spring Cloud release train

Spring Cloud dùng **release train version** dạng `YYYY.N`, ví dụ `2026.0`, `2025.1`. Mỗi train quản lý nhiều project con thông qua BOM `spring-cloud-dependencies`.

BOM là danh mục phiên bản đã được nhóm Spring Cloud kiểm thử cùng nhau. Khi import BOM, ứng dụng không phải tự pin riêng từng version của Gateway, LoadBalancer, Discovery Client hay CircuitBreaker.

### 2.3. Spring Cloud Gateway version

Gateway có version độc lập, ví dụ `5.1.0`, `5.0.5`, `4.3.5`. Một release train có thể quản lý Gateway version khác với số version của train:

| Spring Cloud train | Gateway project version trong train |
| --- | --- |
| `2026.0.0` | `5.1.0` |
| `2025.1.x` | `5.0.x` |
| `2025.0.x` | `4.3.x` |
| `2024.0.x` | `4.2.x` |
| `2023.0.x` | `4.1.x` |

Không suy luận Gateway version bằng cách copy số `2026.0` thành `2026.0.x`. Hãy lấy version từ BOM/release notes của đúng train.

## 3. Ma trận tương thích cần dùng tại ngày 24/11/2026

### 3.1. Ma trận chính

| Spring Cloud Release Train | Spring Boot tương thích | Gateway project version | Nhận định hỗ trợ |
| --- | --- | --- | --- |
| `2026.0.x` (Paddington) | `4.2.x` | `5.1.x` | Train GA mới nhất tại mốc bài |
| `2025.1.x` (Oakwood) | `4.0.x`; `4.1.x` từ `2025.1.2` | `5.0.x` | Train được duy trì |
| `2025.0.x` (Northfields) | `3.5.x` | `4.3.x` | Được đánh dấu EOL OSS trong compatibility table; kiểm Enterprise Support nếu cần |
| `2024.0.x` (Moorgate) | `3.4.x` | `4.2.x` | EOL OSS |
| `2023.0.x` (Leyton) | `3.2.x`, `3.3.x` từ `2023.0.2` | `4.1.x` | EOL OSS |

Bảng này kết hợp thông tin từ Spring Cloud compatibility mapping, release train reference docs và các release của Gateway. Dấu `*` trong bảng tương thích Spring Cloud chính thức có nghĩa release train đã **end of life và không còn được hỗ trợ OSS**. Một version artifact vẫn có thể tồn tại trên Maven Central dù train không còn nhận bản vá cộng đồng.

### 3.2. Phiên bản cụ thể đang được công bố

| Dòng | Mốc phát hành/phiên bản đã xác minh |
| --- | --- |
| Spring Boot `4.2.0` | GA ngày 19/11/2026 |
| Spring Cloud `2026.0.0` | GA ngày 20/11/2026; dựa trên Boot `4.2.0` |
| Spring Cloud Gateway `5.1.0` | Included trong Spring Cloud `2026.0.0` |
| Spring Cloud `2025.1.5` | Reference docs tại mốc bài; Boot `4.0.10` được ghi là supported Boot version |
| Spring Cloud Gateway `5.0.5` | Release thuộc dòng Gateway 5.0.x |
| Spring Cloud `2025.0.3` | Release train cuối được liệt kê trong tài liệu tại mốc bài; Gateway `4.3.5` |
Với `2025.1.x`, Spring Cloud compatibility mapping cho biết Boot `4.1.x` được hỗ trợ bắt đầu từ `2025.1.2`. Không lấy riêng dòng “Supported Boot Version: 4.0.10” của một trang reference để kết luận `4.1.x` không được hỗ trợ; hãy kết hợp compatibility matrix và patch release notes.

### 3.3. Ma trận không đồng nghĩa tất cả tổ hợp đều là khuyến nghị

Có ba câu hỏi độc lập:

| Câu hỏi | Nguồn cần xem |
| --- | --- |
| Boot và Cloud train có tương thích? | Spring Cloud compatibility matrix / train reference |
| Train đang được duy trì OSS không? | Spring Cloud Support và Spring Boot support lifecycle |
| Gateway patch có chứa security fixes cần thiết? | Gateway release notes và Spring Security Advisories |

Ví dụ `Boot 3.5.x + Cloud 2025.0.x + Gateway 4.3.x` là một tổ hợp tương thích theo mapping. Tuy nhiên, Cloud `2025.0.x` đã được đánh dấu EOL OSS trong bảng hiện hành. Nếu hệ thống vẫn phải giữ Boot 3.5 vì ràng buộc, cần xác minh **Enterprise Support** hoặc lập kế hoạch nâng cấp; không xem việc build thành công là bằng chứng hệ thống còn được nhận bản vá OSS.

### 3.4. Cách chọn nhanh

- Dự án mới, chấp nhận nền tảng mới: cân nhắc Boot `4.2.x` + Cloud `2026.0.x` + Gateway `5.1.x`.
- Dự án đang chuyển sang Boot 4 nhưng chưa cần 4.2: dùng train `2025.1.x`, chọn patch tương thích với Boot `4.0.x` hoặc `4.1.x`, và Gateway `5.0.x`.
- Dự án còn ở Boot `3.5.x`: mapping là Cloud `2025.0.x` + Gateway `4.3.x`; kiểm trạng thái EOL/support trước khi quyết định duy trì.
- Dự án ở Boot `3.4.x` hoặc thấp hơn: không khởi đầu một nâng cấp mới bằng train EOL; lập lộ trình lên nhánh còn được hỗ trợ.

## 4. Đừng quản lý version bằng cách pin từng dependency

### 4.1. Maven: dùng Spring Boot parent và Spring Cloud BOM

Ví dụ baseline Boot 4.2.0 + Cloud 2026.0.0 + Gateway Server WebFlux:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

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

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Gateway starter không cần khai báo version riêng; BOM quản lý version của Gateway và các module Spring Cloud. Nếu dự án cần Eureka/Consul/Kubernetes Discovery Client, thêm starter tương ứng **không có version tự pin** khi nó thuộc cùng release train.

Nếu công ty dùng corporate parent POM thay Spring Boot parent, có thể giữ corporate parent và import `spring-boot-dependencies` cùng `spring-cloud-dependencies` theo quy tắc dependency management của tổ chức. Không import nhiều BOM xung đột thứ tự mà không biết version nào đang thắng.

### 4.2. Gradle: import Cloud BOM qua platform

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

group = 'example.gateway'
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
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2026.0.0'
    )

    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là ví dụ tối thiểu. Một dự án thật cần bổ sung test dependencies, security/discovery starter, plugin và build conventions theo runtime thực tế. Nếu dùng `io.spring.dependency-management` plugin để import BOM thay `platform`, giữ một cách quản lý thống nhất.

### 4.3. Không làm những việc sau

~~~xml
<!-- Không nên: tự pin một Gateway version khác với Cloud BOM -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    <version>4.3.5</version>
</dependency>
~~~

Không:

- Pin riêng `spring-cloud-gateway-server`, `spring-cloud-commons`, `spring-cloud-loadbalancer` sang các dòng khác nhau.
- Override Spring Framework, Reactor Netty, Jackson, Spring Security chỉ để hết lỗi compile mà không kiểm dependency constraints.
- Dùng snapshot hoặc milestone trong production nếu không có chính sách chấp nhận pre-release.
- Trộn starter Gateway WebFlux với Gateway Web MVC trong cùng ứng dụng chỉ vì muốn “thử cả hai”.
- Giữ `spring-cloud-starter-parent` cũ làm nguồn quản lý Spring Cloud trong train mới; release notes `2025.1` ghi nhận artifact parent này đã bị loại. Dùng Spring Boot parent hoặc dependency management của Boot kết hợp Cloud BOM.

## 5. Xác minh dependency tree trước khi nâng cấp

### 5.1. Maven

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dverbose
mvn dependency:tree -Dincludes=org.springframework.cloud,org.springframework,io.projectreactor,io.netty,com.fasterxml.jackson.core,tools.jackson
~~~

Kiểm tra:

- Có đúng một version Gateway project theo BOM?
- `spring-cloud-commons` và `spring-cloud-loadbalancer` cùng release train?
- Spring Framework major có đúng với Boot?
- Reactor/Netty có bị dependency bên ngoài kéo lệch?
- Jackson 2 và Jackson 3 có cùng tồn tại có chủ đích, hay do dependency cũ kéo vào?
- Có version override qua corporate BOM, `dependencyManagement`, Maven profile hoặc transitive dependency?

### 5.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-gateway
./gradlew dependencyInsight --dependency spring-cloud-commons
./gradlew dependencyInsight --dependency reactor-netty-http
./gradlew dependencyInsight --dependency jackson-databind
~~~

Dùng `dependencyInsight` để tìm **ai** đưa version không mong muốn vào graph. Không chỉ đọc danh sách dependency rồi sửa một version trực tiếp.

### 5.3. Kiểm tra build/runtime requirements

Spring Boot 4.2.0 yêu cầu tối thiểu Java 17; tài liệu system requirements tại mốc bài ghi tương thích đến Java 27, Spring Framework 7.1.0 trở lên, Maven 3.6.3+, Gradle 8.x (8.14+) hoặc Gradle 9.x. Các third-party integrations có thể đòi Java/build tool cao hơn.

Đối với Spring Boot 4.0, migration guide cũng ghi Java 17+, Kotlin 2.2+ và GraalVM Native Image 25+ khi sử dụng native-image. Hãy kiểm cả:

- Java version trên developer machine, CI và production image.
- Maven/Gradle Wrapper, không chỉ version cài toàn máy.
- Kotlin/Groovy compiler, annotation processors và code generators.
- Docker base image, buildpacks và native-image toolchain.
- Servlet container nếu chọn Gateway Web MVC.
- TLS provider/certificate store, DNS và OS packages trong runtime image.

### 5.4. Tạo một baseline có thể so sánh

Trước khi thay version, lưu:

~~~text
Baseline:
  Spring Boot:
  Spring Cloud Release Train:
  Spring Cloud Gateway:
  Java:
  Maven/Gradle:
  Gateway runtime: WebFlux / Web MVC
  Discovery client:
  Route count:
  Filter inventory:
  Security configuration:
  TLS/forwarded-header configuration:
  Actuator exposure:
  Build/test result:
  Request throughput and latency:
~~~

Lưu dependency tree, startup logs đã redact, test report và các metrics quan trọng. Nếu không có baseline, khó xác định regression do dependency, property migration hay môi trường.

## 6. Chuyển từ Boot 3.5 / Gateway 4.3 sang Boot 4 / Gateway 5

Đây là thay đổi lớn hơn một lần nâng patch. Spring Boot 4 có modular design, Spring Framework 7, Jakarta EE 11 và Jackson 3; Spring Cloud 2025.1 có breaking changes để tương thích với nền tảng này.

### 6.1. Bước chuẩn bị: cập nhật dòng 3.5 trước

Migration guide Spring Boot 4 khuyến nghị nâng ứng dụng lên **bản mới nhất của Spring Boot 3.5.x** trước khi chuyển sang Boot 4. Việc này giúp xử lý deprecated APIs và dependency updates ngay trên nền cũ, giảm số biến cùng thay đổi trong một lần nâng cấp.

Trước khi chuyển:

1. Nâng Boot 3.5 lên patch mới nhất phù hợp với support contract.
2. Dùng Spring Cloud train tương thích Boot 3.5 để cập nhật Gateway 4.3.x tới patch mới nhất của dòng.
3. Xử lý deprecated methods/properties đang cảnh báo.
4. Chạy toàn bộ route, filter, security, TLS, discovery và load tests.
5. Lưu dependency tree, test evidence và rollback artifact.

**Lưu ý:** tại mốc bài, Cloud `2025.0.x` bị đánh dấu EOL OSS. Đây là bước ổn định hóa legacy baseline, không phải khuyến nghị tiếp tục ở nhánh này lâu dài. Nếu cần hỗ trợ kéo dài, xác nhận quyền Enterprise Support.

### 6.2. Runtime requirements và nền tảng Jakarta

Spring Boot 4 yêu cầu Spring Framework 7 và dựa trên Jakarta EE 11. Với Gateway Server Web MVC, Servlet baseline là 6.1; cần kiểm Tomcat/Jetty version và deployment container. Undertow support bị loại khỏi Spring Boot 4.0 do chưa đáp ứng Servlet 6.1 baseline tại thời điểm phát hành.

Gateway Server WebFlux có runtime khác: dùng Spring WebFlux/Reactor Netty và **không triển khai như WAR trong traditional Servlet container**. Không lấy yêu cầu Servlet của Web MVC để suy ra runtime WebFlux.

### 6.3. Spring Boot 4 modularization: rà lại starter

Boot 4 chia modules nhỏ hơn và chuẩn hóa tên starter/package. Nếu ứng dụng phụ thuộc trực tiếp vào một jar cũ hoặc chỉ dựa vào transitive dependency, cần thêm starter/module mới phù hợp.

Một số thay đổi tiêu biểu trong migration guide:

| Boot 3.x / tên cũ | Boot 4.x / hướng mới |
| --- | --- |
| `spring-boot-starter-web` | `spring-boot-starter-webmvc` |
| `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` |
| `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` |
| `spring-boot-starter-oauth2-authorization-server` | `spring-boot-starter-security-oauth2-authorization-server` |
| Module package gộp cũ | Package module chuyên biệt dạng `org.springframework.boot.<module>` |

Không tự đổi tên starter Gateway của Spring Cloud theo quy tắc tên Boot. Ví dụ starter Gateway Server WebFlux vẫn là artifact Spring Cloud `spring-cloud-starter-gateway-server-webflux`; Boot 4 modularization áp dụng cho các starter/module thuộc Spring Boot.

### 6.4. Jackson 3: kiểm custom filters và serializers

Spring Boot 4 dùng Jackson 3 làm JSON library ưu tiên:

- Các group/package chính chuyển từ `com.fasterxml.jackson` sang `tools.jackson`.
- `jackson-annotations` vẫn giữ group/package `com.fasterxml.jackson.core` và `com.fasterxml.jackson.annotation`.
- Một số class/customizer đổi tên để phản ánh Jackson 3.
- Jackson 2 compatibility module `spring-boot-jackson2` có thể dùng tạm khi dependency chưa tương thích, nhưng đây là phương án chuyển tiếp và được đánh dấu deprecated.

Gateway custom filters thường parse hoặc mutate JSON body bằng `ObjectMapper`, codec và message readers/writers. Kiểm tra:

- Imports của `ObjectMapper`, `JsonNode`, serializers/deserializers.
- Custom `HttpMessageReader`/`HttpMessageWriter`.
- `ModifyRequestBody`/`ModifyResponseBody` rewrite functions.
- Custom error response/problem details.
- Third-party libraries chỉ hỗ trợ Jackson 2.
- Test body encoding, content type, null handling, date/time và polymorphic payloads.

Không thêm Jackson 2 và Jackson 3 một cách tùy tiện rồi giả định auto-configuration sẽ chọn mapper đúng. Nếu phải duy trì cả hai, định nghĩa mapper/codec và ranh giới sử dụng rõ ràng.

### 6.5. JSpecify nullability và Spring Framework 7

Spring Cloud 2025.1 release notes nêu breaking changes liên quan JSpecify nullability và Spring Framework 7. Điều này có thể làm lộ các giả định nullability trong custom code:

- Custom `GatewayFilterFactory` và `GlobalFilter`.
- `RouteDefinitionLocator`, `ServiceInstanceListSupplier`.
- Custom `HttpHeadersFilter`.
- Java/Kotlin interoperability.
- Overridden methods và generic return types.
- Build warnings từ static analysis/compiler.

Khi nâng, đọc lại method signatures và null contracts từ thư viện mới. Đừng chỉ suppress warning hàng loạt; warning có thể chỉ ra code từng giả định một giá trị luôn non-null nhưng framework mới đã khai báo khác.

### 6.6. Configuration properties migrator

Spring Boot 4 có thể đổi hoặc loại property. `spring-boot-properties-migrator` giúp chẩn đoán và tạm thời migrate một số property khi khởi động.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Gradle:

~~~groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
~~~

Dùng nó trong môi trường migration/test, đọc hết diagnostics, cập nhật file cấu hình sang tên mới rồi **gỡ migrator** khỏi dependency graph sau khi hoàn tất. Không giữ migrator như một giải pháp production lâu dài.

### 6.7. Spring Cloud 2025.1: BOM và breaking changes

Train `2025.1` chuyển sang thế hệ Spring Framework 7/Boot 4, đồng thời có thay đổi tương thích Jackson 3 và JSpecify. Release notes ghi nhận artifact `spring-cloud-starter-parent` đã bị loại. Dùng Spring Boot parent hoặc dependency management của Boot, sau đó import Cloud BOM.

Không trộn Spring Cloud `2025.0.x` với Boot 4 chỉ vì artifact vẫn resolve được; train đúng cho Boot 4.0/4.1 là `2025.1.x`.

## 7. Thay đổi Spring Cloud Gateway cần rà soát

### 7.1. Property namespace chuyển trong train 2025.0

Spring Cloud Gateway đổi prefixes để phản ánh tên module/starter cụ thể:

| Runtime/module | Prefix cũ | Prefix mới |
| --- | --- | --- |
| Gateway Server WebFlux | `spring.cloud.gateway.*` | `spring.cloud.gateway.server.webflux.*` |
| Gateway Server Web MVC | `spring.cloud.gateway.mvc.*` | `spring.cloud.gateway.server.webmvc.*` |
| Proxy Exchange WebFlux | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webflux.*` |
| Proxy Exchange Web MVC | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webmvc.*` |

Ví dụ một cấu hình cũ:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: lb://ORDER-SERVICE
          predicates:
            - Path=/api/orders/**
~~~

Với Gateway Server WebFlux theo namespace mới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
~~~

Đây là thay đổi quan trọng: nếu giữ prefix cũ trong một bản Gateway đã migrate, route có thể không được bind như kỳ vọng. Hãy chuyển toàn bộ file `application.yml`, profile overlays, Config Server, Helm values, environment variables, ConfigMaps và tests.

### 7.2. Đừng đổi nhầm prefix WebFlux sang Web MVC

Gateway Server WebFlux và Gateway Server Web MVC có namespace riêng. Không lấy YAML WebFlux rồi thay chữ `webflux` bằng `webmvc` một cách máy móc; hai runtime khác API, filters, server và execution model.

Kiểm starter:

- WebFlux: `spring-cloud-starter-gateway-server-webflux`.
- Web MVC: `spring-cloud-starter-gateway-server-webmvc`.
- Proxy Exchange: các starter `spring-cloud-gateway-proxyexchange-*` tương ứng release.

Gateway WebFlux dựa trên Spring WebFlux/Reactor Netty. Gateway Web MVC dùng Spring WebMvc.fn/Servlet stack. Chọn một runtime theo kiến trúc; không trộn starter và assumptions của hai runtime.

### 7.3. Forwarded headers và trusted proxies

Trong các fix versions được Spring Cloud Gateway release notes mô tả, chức năng `Forwarded` và `X-Forwarded-*` bị **disabled by default** để tránh tin dữ liệu từ untrusted proxies.

Nếu ứng dụng cần forwarding metadata, khai báo trusted proxy identities bằng Java regular expression. Ví dụ Gateway Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^10[.]20[.]0[.](?:10|11)$'
~~~

Đây chỉ là ví dụ regex cho hai proxy identities; không phải CIDR và không thay NetworkPolicy/firewall. Phải kiểm chính xác format proxy metadata ở môi trường thực, sanitize headers ở edge và chặn direct access bypass ingress.

Với Gateway Server Web MVC, property dùng namespace riêng theo tài liệu release. Không đặt regex WebFlux vào Web MVC rồi mặc định nó có tác dụng.

### 7.4. Kiểm filter order sau nâng cấp

Gateway 5.1.0 có tài liệu/bổ sung làm rõ thứ tự default filters và route filters. Những custom filters phụ thuộc thứ tự có thể thay đổi behavior sau nâng cấp.

Kiểm:

- `GlobalFilter` order và `Ordered`.
- `default-filters` so với route-specific filters.
- `NettyRoutingFilter` và response write stage.
- Security/auth filters trước route match.
- Request body cache/modify và response body rewrite.
- Retry/CircuitBreaker/fallback.
- Custom `HttpHeadersFilter`.
- Filter có side effect hoặc mutate exchange attributes.

Không chỉ kiểm filter được gọi; kiểm **thứ tự** và trạng thái request/response tại thời điểm mỗi filter chạy.

### 7.5. Retry, Reactor và Web MVC

Gateway 5.1 release notes ghi nhận migration từ Reactor Addons Retry sang Framework Core Retry và bổ sung MVC WebSocket support. Nếu dự án có custom retry logic, kiểm import/types và semantics retry/caching. Với Web MVC, test WebSocket handshake/origin/upgrade theo runtime mới; không suy behavior từ WebFlux.

Retry không được nhân đôi attempts giữa Gateway filter và LoadBalancer. Với POST/payment/order, phải kiểm idempotency key và trạng thái business trước khi cho phép retry.

### 7.6. Security fixes phải là một phần của version selection

Không chọn version chỉ vì tương thích compile. Tại mốc bài:

- Gateway `5.0.2` có fix cho CVE-2026-47825.
- Gateway `5.0.3` có fix CVE-2026-47879 liên quan SSRF/native file access với gRPC.
- Gateway `5.0.5` có fixes CVE-2026-59425, CVE-2026-59426, CVE-2026-59427 và CVE-2026-59428: JsonToGrpc resource leak, LocalResponseCache cross-route leak, cache private/no-store response, và WebSocket same-origin enforcement.
- Spring Cloud `2026.0.0` bao gồm Gateway `5.1.0` và liệt kê các fixes security tương ứng trong release train notes.

Đây là ví dụ vì sao phải dùng **patch mới nhất trong train phù hợp**. Đừng chọn Gateway `5.0.1` chỉ vì đó là version đầu tiên build được trên Boot 4.0; kiểm security advisories, release notes và dependency tree trước khi deploy.

## 8. Quy trình chọn ma trận trước khi nâng cấp

### Bước 1 — Ghi lại trạng thái hiện tại

Thu thập:

- Spring Boot version.
- Spring Cloud BOM version.
- Gateway artifact version thực sự được resolve.
- Runtime WebFlux hay Web MVC.
- Java và build tool versions.
- Discovery client, LoadBalancer, CircuitBreaker, Redis/rate limiter.
- Custom filters/predicates và dependency bên thứ ba.
- Config Server/Helm/ConfigMaps/profiles.
- Security advisories và support contract.

### Bước 2 — Chọn Boot target trước

Chọn Boot version theo yêu cầu runtime, Java, Servlet/Netty, vendor support và dependencies. Sau đó tra Spring Cloud release train tương thích với Boot đó.

Không bắt đầu bằng cách tìm “Gateway mới nhất” rồi cố nhét vào Boot hiện tại.

### Bước 3 — Chọn Cloud BOM

Dựa trên Boot target:

~~~text
Boot 4.2.x       -> Cloud 2026.0.x -> Gateway 5.1.x
Boot 4.0/4.1.x   -> Cloud 2025.1.x -> Gateway 5.0.x
Boot 3.5.x       -> Cloud 2025.0.x -> Gateway 4.3.x (EOL OSS tại mốc bài)
~~~

Dùng latest compatible service release của train. Kiểm release notes để biết version Gateway cụ thể do BOM quản lý.

### Bước 4 — Kiểm support lifecycle và security

Trả lời:

- Train còn OSS supported?
- Boot version có được Spring duy trì?
- Có Enterprise Support contract nếu cần?
- Gateway patch đã có các CVE fixes liên quan?
- Có dependency third-party nào chưa hỗ trợ Boot/Framework/Jackson major mới?

Nếu chưa có câu trả lời, chưa nên chọn production target.

### Bước 5 — Đọc migration guide theo cả ba project

Đọc:

1. Spring Boot release notes/migration guide.
2. Spring Cloud train release notes.
3. Spring Cloud Gateway release notes.
4. Spring Framework/Spring Security release notes nếu major đổi.
5. Security advisories liên quan Gateway, Netty, Reactor, Jackson và discovery clients.

Không chỉ đọc trang “What’s New”; phần breaking changes và security fixes mới quyết định rủi ro.

### Bước 6 — Resolve BOM và dependency tree

Cập nhật Boot parent/plugin + Cloud BOM, sau đó chạy dependency tree. Loại bỏ version overrides không cần thiết và xử lý dependency chưa tương thích.

### Bước 7 — Chuyển property/starter và custom code

Rà:

- Gateway property prefixes.
- Starter artifact names.
- Boot property renames/removals.
- Jackson 3, JSpecify, Framework 7.
- Forwarded headers/trusted proxies.
- Custom filters và filter ordering.
- WebSocket, gRPC, body codecs và native image hints.

### Bước 8 — Chạy test theo behavior, không chỉ compile

Chạy unit/integration/security/contract/performance tests. Các bài test bắt buộc cho Gateway ở mục 10.

### Bước 9 — Canary và rollout

Deploy canary, quan sát request success/error rates, p95/p99 latency, route misses, upstream failures, retry counts, circuit breaker state, memory/pool metrics và security logs.

### Bước 10 — Xác nhận rollback

Lưu image/artifact và cấu hình trước nâng cấp. Đảm bảo rollback không khiến schema/config/route definitions mới không tương thích với phiên bản cũ.

## 9. Kế hoạch nâng cấp theo từng giai đoạn

### 9.1. Ví dụ từ Boot 3.5 / Cloud 2025.0 / Gateway 4.3 sang Boot 4.2 / Cloud 2026.0 / Gateway 5.1

Có thể chia thay đổi thành các chặng:

~~~text
Current:
  Boot 3.5.x
  Cloud 2025.0.x
  Gateway 4.3.x

Stabilize current line:
  update to latest compatible patches
  capture dependency/test/metrics baseline

Intermediate Boot 4 line:
  Boot 4.0.x or 4.1.x
  Cloud 2025.1.x
  Gateway 5.0.x
  migrate Boot 4 + Gateway namespace/starter/API changes

Target:
  Boot 4.2.x
  Cloud 2026.0.x
  Gateway 5.1.x
  update security patches and validate behavior again
~~~

Không bắt buộc mọi dự án phải triển khai hai lần production. Một dự án có test coverage tốt có thể thử nâng trực tiếp sang tổ hợp cuối; nhưng vẫn nên chia **commit/change set** theo lớp: dependency baseline, Boot migration, Cloud/Gateway migration, security/config migration. Cách này giúp cô lập lỗi và review.

### 9.2. Không nâng đồng thời mọi dependency không liên quan

Ví dụ cùng lúc thay Gateway, Redis, discovery provider, service mesh, database driver, Java runtime và deployment platform sẽ khiến việc tìm root cause rất khó. Ưu tiên một nhóm thay đổi có thể kiểm thử độc lập; chỉ nâng dependency bắt buộc theo BOM hoặc security fixes.

### 9.3. Cập nhật cấu hình theo nguồn

Một property có thể tồn tại ở nhiều nơi:

~~~text
application.yml
application-prod.yml
Config Server repository
Kubernetes ConfigMap
Helm values
environment variables
CI/CD pipeline
secret/config injection
~~~

Tìm và sửa tất cả nguồn có hiệu lực. Nếu chỉ sửa `application.yml` nhưng Config Server production vẫn ghi đè prefix cũ, route có thể không được tạo.

## 10. Bộ kiểm thử bắt buộc cho Spring Cloud Gateway

### 10.1. Routing và path

- Route ID và predicate match đúng.
- Host, Path, Method, Header, Query, Cookie predicates giữ behavior.
- `StripPrefix`, `RewritePath`, `PrefixPath`, `SetPath` đúng.
- Trailing slash, encoded slash, Unicode, query string và path traversal cases.
- No-route response không bị biến thành route khác.

### 10.2. Filter chain

- GlobalFilter order và `Ordered`.
- Default filters so với route filters.
- Request header add/remove/set/map.
- Response header add/remove/dedupe.
- Request/response body rewrite và codec.
- `DataBuffer` release, backpressure và cancellation.
- Retry/CircuitBreaker/fallback ordering.
- Filter errors trước/sau response commit.

### 10.3. Service discovery và load balancing

- `lb://SERVICE-ID` có chọn đúng instance.
- Registry empty list và service instance unavailable.
- Health/zone/hint/version filters.
- Retry next instance và retry counts.
- Instance metadata `isSecure`, hostname/port.
- DNS và network policy từ Gateway tới backend.
- Discovery cache refresh khi scale/deploy.

### 10.4. Security và forwarding

- JWT/OAuth2 authentication và scope authorization.
- `Forwarded`/`X-Forwarded-*` từ untrusted client không được tin.
- Trusted proxy regex đúng format/addresses.
- HSTS, CORS, CSP, cookie attributes và public redirect.
- Header size, malformed headers, Host poisoning và request smuggling protections.
- Actuator management endpoints không bị public.
- CVE fixes trong Gateway/Netty/serialization dependencies.

### 10.5. Resilience và HTTP client

- Connect/response/pool acquire timeout.
- Connection pool active/idle/pending metrics.
- TLS truststore, certificate SAN, SNI và mTLS.
- Retry không làm duplicate POST side effects.
- Circuit breaker state/fallback không giả business success.
- Backend 429/503/504 và `Retry-After`.
- Streaming response, chunking, gzip và client cancellation.

### 10.6. Gateway Web MVC/WebFlux khác nhau

Nếu dự án thay runtime:

| Hạng mục | WebFlux | Web MVC |
| --- | --- | --- |
| Programming model | Reactive `ServerWebExchange`/Project Reactor | Servlet/WebMvc.fn |
| HTTP runtime | Reactor Netty | Servlet container phù hợp |
| Filter API | `GlobalFilter`, `GatewayFilter`, `WebFilter` | Handler Filter Functions/Servlet filters |
| Blocking library | Có thể gây block event loop | Phù hợp hơn với imperative code, nhưng vẫn cần sizing |
| Deployment | Netty runtime; không đóng gói WAR truyền thống | Có thể dùng Servlet container |

Chuyển WebFlux sang Web MVC là **thay đổi kiến trúc**, không phải một dòng starter rename. Phải kiểm lại custom filters, security, connection pools, streaming, timeout, WebSocket và metrics.

## 11. Theo dõi sau nâng cấp

### 11.1. Metrics cần so sánh với baseline

| Metric/behavior | Cần phát hiện |
| --- | --- |
| Gateway request count theo route | Route không còn match hoặc bị duplicate |
| 4xx/5xx theo route/outcome | Status mapping thay đổi |
| Upstream latency p50/p95/p99 | Regression ở HTTP client hoặc backend |
| Retry attempts | Tăng attempts ngoài dự kiến |
| Circuit breaker open/half-open | Failure threshold/slow calls đổi |
| LoadBalancer selection failures | Discovery list rỗng hoặc supplier behavior |
| Connection pool pending acquire | Pool saturation |
| JVM heap/direct memory/GC | Buffering/codec/filter changes |
| TLS handshake failures | Truststore/SNI/protocol drift |
| CORS/redirect/auth errors | Browser contract bị thay đổi |

### 11.2. Log/trace

Ghi route ID, outcome, status, latency, upstream attempt count và error category. Không log Authorization, cookies, request body nhạy cảm hoặc raw forwarded headers. Tracing giúp liên kết Gateway và backend nhưng không thay contract tests.

### 11.3. Canary

- Chỉ route một phần traffic vào Gateway mới.
- So p95/p99, 5xx, 429, retries, pool pressure và backend load.
- Chạy synthetic requests cho login, order creation, upload, streaming và WebSocket.
- Kiểm từng replica nhận cùng config và dependency version.
- Tăng tỷ lệ traffic sau khi error budget và SLO không xấu đi.

## 12. Rollback và tương thích cấu hình

Rollback không chỉ là đổi Docker image về version cũ.

Trước nâng cấp, kiểm:

- Config mới có còn được Boot/Gateway cũ hiểu không?
- Config Server có versioned release/rollback?
- Route definitions dynamic có field mới hoặc semantics mới không?
- Redis/cache data có thay đổi serialization/schema?
- JWT/session/cookie/forwarded-header policy có thay đổi không?
- External clients có phụ thuộc status/header/body mới?
- Database migration có backward-compatible không?

Với Gateway, đặc biệt chú ý route configuration và filter properties: nếu bản mới đã chuyển namespace `spring.cloud.gateway.server.webflux.*`, bản cũ có thể không đọc cấu hình mới. Giữ một bản cấu hình có thể dùng cho rollback hoặc chuẩn bị hai manifests riêng, và kiểm bằng integration test.

## 13. Bài thực hành: xây một ma trận nâng cấp có thể review

**Bối cảnh:** Một Gateway WebFlux đang dùng Boot 3.5.x, Cloud 2025.0.x và Gateway 4.3.x. Hệ thống dùng `lb://ORDER-SERVICE`, Redis rate limiter, JWT Resource Server, custom `GlobalFilter`, forwarded headers qua ingress và Reactor Netty.

### Yêu cầu

1. Ghi versions hiện tại từ dependency tree, không chỉ `pom.xml`.
2. Xác định Boot target 4.2.x và Cloud train tương ứng.
3. Xác định Gateway version do BOM target quản lý.
4. Kiểm support lifecycle của train hiện tại và target.
5. Lập danh sách Boot 4 changes: Java, Framework, Jakarta, modular starters, Jackson 3, property migration.
6. Lập danh sách Gateway changes: property namespace, forwarded headers, starter/runtime, filter order.
7. Kiểm CVE advisories và chọn patch release.
8. Cập nhật Maven hoặc Gradle bằng BOM, bỏ version overrides không cần.
9. Chạy dependency tree và xác nhận không có Spring Framework/Netty/Jackson conflict.
10. Chạy tests cho route predicates, filter order, body transformation và path rewriting.
11. Test JWT/authorization, CORS, cookies và forwarded proxy trust.
12. Test service discovery, LoadBalancer, Redis rate limiter và circuit breaker.
13. Test TLS/mTLS, connect/response timeout, WebSocket/gRPC nếu có.
14. Test Actuator exposure và health/readiness.
15. Chạy performance baseline/canary và lập rollback plan.

### Bảng kết quả cần bàn giao

| Hạng mục | Current | Target | Evidence | Trạng thái |
| --- | --- | --- | --- | --- |
| Boot | 3.5.x | 4.2.x | Effective POM/dependency tree | |
| Cloud train | 2025.0.x | 2026.0.x | BOM version | |
| Gateway | 4.3.x | 5.1.x | Resolved artifact | |
| Java/build tool | | | CI build | |
| Runtime | WebFlux | WebFlux | Startup/runtime test | |
| Gateway properties | old prefix | new prefix | Config binding/startup logs | |
| Forwarded headers | current policy | trusted proxies | Spoofing integration test | |
| Route/filter tests | | | WebTestClient/contract tests | |
| Discovery/LB | | | Mock/registry test | |
| Security/CVEs | | | Advisory checklist | |
| Performance | | | Load test report | |
| Rollback | | | Rollback rehearsal | |

### Tiêu chí nghiệm thu

~~~text
[PASS] Boot, Cloud train và Gateway thuộc cùng một compatibility line
[PASS] Các phiên bản được xác minh từ BOM/dependency tree
[PASS] Support lifecycle và Enterprise/OSS support đã được xác nhận
[PASS] Không còn starter/property prefix cũ ngoài chủ đích
[PASS] Không có dependency override xung đột
[PASS] Gateway routes, predicates và filter order đúng
[PASS] Discovery, load balancing, retry và circuit breaker đúng
[PASS] Forwarded headers chỉ tin proxy được chỉ định
[PASS] TLS, CORS, JWT, cookies và WebSocket/gRPC theo contract
[PASS] Security advisories và CVE fixes đã được xử lý
[PASS] Tests, performance baseline và canary đạt
[PASS] Rollback config/image đã được diễn tập
~~~

Đây là tiêu chí lab; cần điền kết quả thực tế của dự án trước khi phê duyệt production.

## 14. Checklist trước khi chọn version production

- [ ] Xác định chính xác Spring Boot, Spring Cloud BOM và Gateway artifact hiện tại.
- [ ] Tra Boot compatibility matrix của Spring Cloud release train.
- [ ] Xác nhận Gateway version thuộc đúng train.
- [ ] Kiểm train còn OSS support hay cần Enterprise Support.
- [ ] Chọn latest compatible patch/service release.
- [ ] Kiểm security advisories của Gateway, Spring Framework, Netty, Reactor và Jackson.
- [ ] Kiểm Java, Kotlin, Maven/Gradle, GraalVM và container runtime requirements.
- [ ] Import BOM thay vì pin version từng project.
- [ ] Xóa version override không cần thiết.
- [ ] Kiểm dependency tree/effective POM.
- [ ] Đọc Boot migration guide, Cloud release notes và Gateway release notes.
- [ ] Chuyển starter/property namespaces phù hợp.
- [ ] Kiểm Jackson 3/JSpecify/Framework 7 nếu lên Boot 4.
- [ ] Kiểm custom filters và filter order.
- [ ] Kiểm WebFlux vs Web MVC runtime assumptions.
- [ ] Kiểm forwarded headers/trusted proxies và route configuration.
- [ ] Test service discovery, LoadBalancer, Redis, retry và circuit breaker.
- [ ] Test request/response body, streaming, TLS, WebSocket và gRPC nếu dùng.
- [ ] Test Actuator, auth, CORS, cookies và redirects.
- [ ] Có baseline metrics và test report trước/sau.
- [ ] Có canary, rollback image và rollback config.

## 15. Tổng kết và tài liệu tham khảo

Trước khi nâng cấp Spring Cloud Gateway, hãy xác định **Spring Boot version trước, chọn Spring Cloud Release Train tương thích sau, rồi lấy Gateway version do BOM quản lý**. Đừng xem số version của ba project là một chuỗi giống nhau và đừng nhầm “dependency resolve được” với “được hỗ trợ”.

Tại mốc 24/11/2026, các đường chính là Boot `4.2.x` + Cloud `2026.0.x` + Gateway `5.1.x`, hoặc Boot `4.0.x`/`4.1.x` + Cloud `2025.1.x` + Gateway `5.0.x`. Boot `3.5.x` tương thích Cloud `2025.0.x`/Gateway `4.3.x`, nhưng train `2025.0.x` đã được đánh dấu EOL OSS trong compatibility table; cần xác minh Enterprise Support nếu tiếp tục duy trì.

Khi lên Boot 4/Gateway 5, kiểm modular starters, Jackson 3, JSpecify, Spring Framework 7, property prefixes, forwarded headers, filter order và security fixes. Cuối cùng, chứng minh behavior bằng dependency tree, integration tests, security tests và canary/rollback rehearsal.

### Tài liệu tham khảo chính thức

- [Spring Cloud — Compatibility Matrix và hướng dẫn chọn Release Train](https://spring.io/projects/spring-cloud/).
- [Spring Cloud 2026.0.0 Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/2026.0/index.html).
- [Spring Cloud 2025.1.5 Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/2025.1/index.html).
- [Spring Cloud Supported Versions và support policy](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions).
- [Spring Cloud 2026.0.0 Release Announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/).
- [Spring Cloud 2025.1 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.1-Release-Notes).
- [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes).
- [Spring Cloud Gateway Releases](https://github.com/spring-cloud/spring-cloud-gateway/releases).
- [Spring Cloud Gateway 5.0 — How to Include Gateway Server WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/starter.html).
- [Spring Cloud Gateway 4.3 — How to Include Gateway Server WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html).
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
- [Spring Boot 4.2.0 Release Announcement](https://spring.io/blog/2026/11/19/spring-boot-4-2-0-available-now/).
- [Spring Boot 4.2 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).

