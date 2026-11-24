# Chọn Java, Spring Boot và Spring Cloud Release Train tương thích

Module `SPRING_CLOUD_CIRCUIT_BREAKER` sử dụng Spring Cloud CircuitBreaker để bảo vệ lời gọi giữa các dịch vụ khi dependency chậm hoặc không khả dụng. Trước khi cấu hình trạng thái CLOSED, OPEN, HALF_OPEN, fallback hay sliding window, cần chuẩn bị một bộ công cụ có phiên bản tương thích. Java, Spring Boot và Spring Cloud được phát hành theo nhịp riêng; chọn đúng từng phiên bản nhưng ghép sai release train vẫn có thể khiến ứng dụng không khởi động hoặc gặp lỗi liên kết thư viện.

Bài này hướng dẫn chọn JDK, chọn Spring Boot, ghép đúng Spring Cloud Release Train, khai báo BOM và kiểm tra môi trường cho dự án dùng Resilience4j. Các phiên bản cụ thể là ví dụ hiện hành tại thời điểm biên soạn; khi bắt đầu dự án mới hoặc nâng cấp, hãy xác nhận lại ma trận tương thích và vòng đời hỗ trợ trên trang Spring chính thức.

## 1. Hiểu vai trò của từng phiên bản

Một dự án Spring Cloud CircuitBreaker có một số lớp phiên bản liên quan:

| Thành phần | Vai trò | Điều cần chọn |
|---|---|---|
| JDK | Biên dịch và chạy ứng dụng Java | Phiên bản nằm trong phạm vi Spring Boot và thư viện dự án hỗ trợ |
| Spring Boot | Cung cấp nền tảng ứng dụng, auto-configuration, quản lý dependency nền tảng | Một phiên bản ổn định thuộc nhánh được Spring Cloud Release Train hỗ trợ |
| Spring Cloud Release Train | BOM tập hợp các phiên bản Spring Cloud tương thích với nhau và với một thế hệ Spring Boot | Train tương ứng chính xác với nhánh Spring Boot |
| Spring Cloud CircuitBreaker | Abstraction để gọi Circuit Breaker theo API thống nhất | Phiên bản do Spring Cloud BOM quản lý |
| Resilience4j | Bộ triển khai Circuit Breaker, Retry, Bulkhead và các cơ chế resilience | Phiên bản được starter của Spring Cloud quản lý |
| Maven hoặc Gradle | Công cụ giải dependency và build | Phiên bản đáp ứng yêu cầu của Spring Boot và dự án |

Không nên chọn từng phiên bản Spring Cloud project bằng cách nhìn phiên bản mới nhất trên Maven Central. Ví dụ, Spring Cloud CircuitBreaker, Spring Cloud Commons và Spring Cloud Config thuộc cùng một release train; BOM giúp các thư viện này dùng những phiên bản đã được kiểm thử cùng nhau.

Cũng cần phân biệt JDK cài trên máy với phiên bản Java mà dự án nhắm tới. Máy có thể cài nhiều JDK, nhưng IDE, Maven, Gradle và CI phải cùng dùng JDK dự kiến. Nếu terminal chạy Java 21 còn IDE chạy Java 17, lỗi build có thể chỉ xuất hiện ở một môi trường.

## 2. Chọn một bộ phiên bản làm chuẩn

Tại thời điểm biên soạn, có thể dùng bộ phiên bản minh họa sau cho dự án mới:

| Thành phần | Phiên bản ví dụ | Ghi chú |
|---|---:|---|
| JDK | 21 LTS | Mức nền thực tế, được Spring Boot 4.0 hỗ trợ |
| Spring Boot | 4.0.10 | Bản vá cụ thể của nhánh 4.0.x |
| Spring Cloud Release Train | 2025.1.5 (Oakwood) | Tương thích Spring Boot 4.0.x và 4.1.x |
| Gradle | 8.14 trở lên trong nhánh 8.x, hoặc 9.x | Spring Boot 4.0 yêu cầu Gradle 8.14+ hoặc 9.x |
| Maven | 3.6.3 trở lên | Phiên bản tối thiểu được Spring Boot 4.0 hỗ trợ |

Spring Boot 4.0.10 yêu cầu tối thiểu Java 17 và tương thích tới Java 27. Vì vậy JDK 21 là lựa chọn LTS phù hợp cho ví dụ; có thể dùng JDK 25 nếu IDE, plugin build và các thư viện còn lại trong dự án cũng hỗ trợ. Không cần dùng JDK mới nhất chỉ vì nó mới hơn: hãy chọn phiên bản đã được kiểm tra trong cả môi trường phát triển lẫn môi trường triển khai.

Spring Cloud 2025.1.5 được công bố ngày 20-11-2026 và tương thích với Spring Boot 4.0.x, 4.1.x. Nếu dự án đang dùng Spring Boot 3.5.x, release train tương ứng là Spring Cloud 2025.0.x. Không ghép Spring Boot 4.0.x với Spring Cloud 2025.0.x; đây là hai thế hệ không tương thích theo ma trận release train.

Ma trận tham khảo các thế hệ thường gặp:

| Spring Boot | Spring Cloud Release Train | Ghi chú |
|---|---|---|
| 4.0.x, 4.1.x | 2025.1.x (Oakwood) | Dùng bản service release mới nhất được công bố cho train |
| 3.5.x | 2025.0.x (Northfields) | Phù hợp với ứng dụng đang ở thế hệ Boot 3.5 |
| 3.4.x | 2024.0.x (Moorgate) | Nhánh cũ hơn; kiểm tra tình trạng hỗ trợ trước khi chọn cho dự án mới |
| 3.2.x, 3.3.x | 2023.0.x (Leyton) | Nhánh cũ; chỉ dùng khi có ràng buộc tương thích cụ thể |

Bảng này mô tả quan hệ tương thích giữa các thế hệ, không khẳng định mọi bản vá của các nhánh đều còn được hỗ trợ. Trước khi quyết định, kiểm tra trang Spring Cloud để biết release train nào còn trong thời gian hỗ trợ và lấy bản service release mới nhất của train đó.

## 3. Kiểm tra JDK và công cụ build

Cài JDK đầy đủ thay vì chỉ cài JRE. JDK cung cấp compiler `javac`, công cụ chẩn đoán và runtime cần thiết để build ứng dụng.

Trên terminal, kiểm tra:

```bash
java -version
javac -version
```

Hai lệnh nên hiển thị cùng thế hệ JDK. Kiểm tra thêm biến môi trường:

- `JAVA_HOME` trỏ tới thư mục JDK mong muốn.
- `PATH` ưu tiên `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên Linux/macOS.
- IDE được cấu hình dùng cùng JDK cho Project SDK, Maven importer và Gradle JVM.
- CI dùng JDK cùng thế hệ với môi trường phát triển.

Kiểm tra Maven:

```bash
mvn -v
```

Kiểm tra Gradle Wrapper của dự án:

```bash
./gradlew -version
```

Trên Windows có thể chạy:

```powershell
.\gradlew.bat -version
```

Gradle Wrapper lưu phiên bản Gradle trong dự án, giúp mọi thành viên và CI sử dụng cùng một build tool mà không phụ thuộc Gradle cài toàn cục. Với Maven, có thể dùng Maven Wrapper (`./mvnw` hoặc `mvnw.cmd`) để ghim phiên bản Maven cho dự án.

Không chỉ kiểm tra `java -version` trong terminal. Maven và Gradle có thể được khởi chạy bởi một JDK khác do `JAVA_HOME`, IDE hoặc cấu hình daemon. Đọc phần JVM trong kết quả `mvn -v` và `gradlew -version` để xác nhận chính xác.

## 4. Tạo dự án bằng Spring Initializr

Spring Initializr giúp tạo skeleton dự án với phiên bản Spring Boot và build tool đã chọn.

1. Mở [Spring Initializr](https://start.spring.io).
2. Chọn Project là Gradle hoặc Maven theo chuẩn của nhóm.
3. Chọn ngôn ngữ Java.
4. Chọn Spring Boot 4.0.10 trong bộ ví dụ này.
5. Đặt Group, Artifact, Name và Packaging phù hợp.
6. Chọn Java 21.
7. Thêm các starter ứng dụng cần thiết, ví dụ Spring Web MVC hoặc WebFlux và Spring Boot Actuator.
8. Generate, giải nén và mở dự án trong IDE.

Spring Initializr có thể quản lý các phiên bản nền tảng khi tạo dự án. Sau khi sinh dự án, vẫn cần thêm Spring Cloud BOM tương thích và starter CircuitBreaker. Không tự thêm nhiều phiên bản Spring Cloud riêng lẻ vào từng dependency.

Nếu đang làm việc trên một repository có sẵn, hãy đọc cấu hình build hiện có trong chính dự án trước khi nâng cấp. Giữ nguyên build tool và nhánh Spring Boot nếu có ràng buộc của ứng dụng; xác định release train tương ứng rồi mới thay đổi phiên bản. Không nâng riêng Spring Cloud CircuitBreaker mà bỏ qua Spring Cloud BOM.

## 5. Khai báo Spring Cloud BOM với Gradle

BOM (Bill of Materials) là tập hợp dependency constraints, giúp Gradle chọn các phiên bản Spring Cloud đã được nhóm release train kiểm thử. Với Gradle Groovy DSL, cấu hình minh họa như sau:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.0.10'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2025.1.5')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Nếu dự án dùng Kotlin DSL (`build.gradle.kts`), có thể khai báo tương đương:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.0.10"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

extra["springCloudVersion"] = "2025.1.5"

dependencyManagement {
    imports {
        mavenBom("org.springframework.cloud:spring-cloud-dependencies:${property("springCloudVersion")}")
    }
}

dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Trong cả hai ví dụ, không ghi version trực tiếp cho `spring-cloud-starter-circuitbreaker-resilience4j`. Spring Cloud BOM sẽ quản lý phiên bản tương ứng. Plugin Spring Boot quản lý các dependency Spring Boot; Spring Cloud BOM quản lý các dependency thuộc hệ sinh thái Spring Cloud. Hai cơ chế này bổ sung cho nhau.

Nếu dự án dùng Gradle mà không dùng plugin `io.spring.dependency-management`, có thể import BOM bằng native Gradle platform:

```groovy
dependencies {
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2025.1.5')
    implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
}
```

Chỉ chọn một cách quản lý BOM nhất quán trong dự án. Tránh import nhiều release train khác nhau hoặc khai báo phiên bản thủ công làm ghi đè dependency do BOM quản lý.

## 6. Khai báo Spring Cloud BOM với Maven

Nếu dùng Maven, Spring Boot parent quản lý dependency và plugin phổ biến của Spring Boot. Import Spring Cloud BOM trong `dependencyManagement` để quản lý starter Spring Cloud:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.0.10</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-cloud.version>2025.1.5</spring-cloud.version>
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
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
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
```

Đoạn trên là các phần cần đặt trong thẻ `project` của `pom.xml`; giữ lại các thông tin project, plugin và dependency khác mà ứng dụng đang cần. Nếu không dùng Spring Boot parent, có thể import cả Spring Boot BOM và Spring Cloud BOM, nhưng phải quản lý thứ tự và nguồn version một cách rõ ràng.

Không thêm `<version>` cho starter CircuitBreaker khi BOM đã quản lý. Nếu Maven báo thiếu version, hãy kiểm tra BOM có nằm trong `dependencyManagement` và tọa độ artifact có chính xác hay không.

## 7. Chọn Web MVC hay WebFlux cho bài thực hành

Circuit Breaker của Spring Cloud có thể bao quanh lời gọi đồng bộ và reactive. Hãy chọn stack web theo mô hình xử lý của ứng dụng:

| Nhu cầu | Lựa chọn thường dùng |
|---|---|
| Controller và client đồng bộ, xử lý request theo mô hình Servlet | Spring MVC và HTTP client đồng bộ |
| Pipeline non-blocking, dùng Reactor và WebClient | Spring WebFlux |
| Ứng dụng đang dùng Spring MVC và chỉ cần Circuit Breaker cho lời gọi đồng bộ | Giữ Spring MVC; không cần chuyển toàn bộ ứng dụng sang WebFlux |
| Ứng dụng cần reactive end-to-end | Dùng WebFlux và tránh gọi `block()` trong pipeline |

Việc thêm Resilience4j starter không tự biến ứng dụng thành reactive. Với luồng reactive, cần dùng API `ReactiveCircuitBreakerFactory` và bảo đảm fallback cũng trả về publisher như `Mono` hoặc `Flux`. Với luồng đồng bộ, dùng `CircuitBreakerFactory`. Không trộn hai kiểu gọi trong cùng một pipeline theo cách chặn event loop.

Nếu bài thực hành cần cả hai cách, tạo hai module hoặc hai ví dụ nhỏ riêng biệt. Như vậy dependency và cấu hình của từng kiểu dễ hiểu, dễ kiểm tra hơn.

## 8. Xác minh phiên bản sau khi tạo dự án

Sau khi cấu hình, kiểm tra toolchain và dependency tree trước khi viết logic Circuit Breaker.

Với Gradle:

```bash
./gradlew -version
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean test
```

Trên Windows:

```powershell
.\gradlew.bat -version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat clean test
```

Với Maven:

```bash
mvn -v
mvn dependency:tree
mvn clean verify
```

Trong dependency tree, xác nhận các điểm sau:

- Spring Boot dependencies thuộc đúng nhánh 4.0.x trong ví dụ.
- Spring Cloud dependencies thuộc release train 2025.1.x.
- Spring Cloud CircuitBreaker và Resilience4j được giải từ BOM tương ứng.
- Không có nhiều phiên bản Spring Framework hoặc Spring Cloud Commons cùng xuất hiện do khai báo version thủ công.
- Java compiler và runtime dùng đúng JDK đã chọn.

Spring Cloud có compatibility verifier để phát hiện một số tổ hợp Spring Boot không tương thích khi ứng dụng khởi động. Nếu ứng dụng báo release train không hỗ trợ Spring Boot đang có, hãy sửa phiên bản Boot hoặc Cloud theo ma trận. Không tắt verifier chỉ để bỏ qua lỗi; việc tắt kiểm tra không làm hai thư viện trở nên tương thích.

## 9. Những lỗi môi trường thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `UnsupportedClassVersionError` | Runtime JDK cũ hơn bytecode đã biên dịch | Kiểm tra `java -version`, IDE runtime và cấu hình CI |
| Build thành công trong terminal nhưng IDE báo lỗi | IDE dùng JDK hoặc Gradle JVM khác | Đồng bộ Project SDK, Gradle JVM và Maven importer |
| `Spring Boot ... is not compatible with this Spring Cloud release train` | Ghép sai nhánh Boot và Cloud | Đối chiếu compatibility matrix, chọn release train đúng |
| Dependency Spring Cloud không tìm thấy version | Chưa import BOM hoặc BOM không áp dụng cho dependency | Kiểm tra `dependencyManagement` hoặc `platform(...)` |
| `NoSuchMethodError` hoặc `ClassNotFoundException` khi chạy | Dependency bị lệch phiên bản hoặc bị ghi đè | Kiểm tra dependency tree, loại bỏ version thủ công và dùng BOM |
| Maven/Gradle tải dependency thất bại | Proxy, mạng, repository hoặc cache build lỗi | Kiểm tra repository và proxy; thử refresh dependency khi cần |
| Máy local build được nhưng CI thất bại | JDK, build tool hoặc biến môi trường khác nhau | Dùng Wrapper, ghim JDK toolchain và cấu hình CI tương ứng |

Khi gặp lỗi tương thích, xử lý theo thứ tự: xác nhận JDK đang chạy, xác nhận phiên bản Spring Boot, xác nhận Spring Cloud BOM, sau đó xem dependency tree. Thay đổi một lớp phiên bản mỗi lần sẽ giúp xác định nguyên nhân dễ hơn.

## 10. Checklist chuẩn bị môi trường

Trước khi bắt đầu thực hành Circuit Breaker, hãy xác nhận:

- [ ] Đã cài JDK phù hợp và `java -version` cùng `javac -version` hiển thị đúng.
- [ ] IDE, terminal, Maven/Gradle và CI sử dụng JDK nhất quán.
- [ ] Đã chọn một phiên bản Spring Boot còn được hỗ trợ.
- [ ] Đã chọn Spring Cloud Release Train theo đúng compatibility matrix của Spring Boot.
- [ ] Đã import Spring Cloud BOM và không tự ghim version cho starter do BOM quản lý.
- [ ] Đã thêm starter `spring-cloud-starter-circuitbreaker-resilience4j`.
- [ ] Đã xác định dùng Spring MVC hay WebFlux theo mô hình xử lý.
- [ ] Build tool Wrapper có phiên bản tương thích và build dự án thành công.
- [ ] Compatibility verifier được giữ bật để phát hiện cấu hình không tương thích.

Sau khi checklist đạt, môi trường đã sẵn sàng cho các bài thực hành cấu hình Resilience4j, fallback, timeout, bulkhead, reactive và theo dõi metric. Nếu thay đổi Spring Boot hoặc Spring Cloud về sau, hãy kiểm tra lại toàn bộ ma trận phiên bản trước khi cập nhật.

## Tài liệu tham khảo

- [Spring Cloud — Release Trains và ma trận tương thích](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.5 — thông báo phát hành](https://spring.io/blog/2026/11/20/spring-cloud-2025-1-5-has-been-released/)
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Initializr](https://start.spring.io)
- [Spring Cloud CircuitBreaker Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)


