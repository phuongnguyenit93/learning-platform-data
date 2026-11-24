# Chọn Spring Boot, Spring Cloud Release Train và JDK tương thích

Khi xây dựng microservice có service discovery, ba lớp phiên bản cần được chọn cùng nhau: JDK dùng để biên dịch và chạy ứng dụng, Spring Boot làm nền tảng ứng dụng, và Spring Cloud Release Train quản lý các thư viện cho hệ thống phân tán. Một cặp phiên bản không tương thích có thể khiến ứng dụng dừng ngay lúc khởi động, dù mã nguồn của service discovery không có lỗi.

Bài này dùng thông tin phát hành chính thức tại ngày 24/11/2026. Các phiên bản mới sẽ tiếp tục được phát hành, vì vậy hãy kiểm tra lại bảng tương thích trước mỗi lần tạo dự án hoặc nâng cấp.

## 1. Hiểu vai trò của từng phiên bản

| Thành phần | Vai trò | Cần kiểm tra điều gì? |
|---|---|---|
| JDK | Cung cấp JVM và compiler để biên dịch, chạy ứng dụng Java | Phiên bản tối thiểu/tối đa mà Spring Boot và thư viện bên thứ ba hỗ trợ; JDK thực tế mà IDE, Maven, Gradle và môi trường chạy đang sử dụng |
| Spring Boot | Tạo cấu trúc ứng dụng, quản lý cấu hình, auto-configuration, web server và nhiều dependency nền tảng | Phiên bản Java tối thiểu, build tool được hỗ trợ và các thay đổi giữa các major/minor version |
| Spring Cloud Release Train | Tập hợp các phiên bản Spring Cloud được kiểm thử cùng nhau, bao gồm Discovery, LoadBalancer, Eureka, Consul và các thành phần cloud khác | Release Train nào tương thích với dòng Spring Boot đang dùng; chọn bản service release mới nhất trong train đó |

Spring Boot và Spring Cloud có hai cơ chế quản lý dependency riêng. Spring Boot parent hoặc BOM quản lý các thư viện thuộc Spring Boot. BOM `spring-cloud-dependencies` quản lý các module Spring Cloud. Khi import đúng hai BOM, dependency như `spring-cloud-starter-netflix-eureka-client` thường không cần khai báo version riêng.

Release Train là một nhánh phát hành của cả hệ sinh thái Spring Cloud. Ví dụ `2026.0.0` là phiên bản Release Train; bên trong train đó, Spring Cloud Netflix có phiên bản module riêng. Không lấy số phiên bản của một module rồi điền vào `spring-cloud.version`.

## 2. Tra bảng tương thích Spring Boot và Spring Cloud trước

Không chọn Spring Cloud chỉ vì đó là phiên bản mới nhất. Hãy xác định dòng Spring Boot trước, sau đó chọn Release Train được Spring công bố tương thích với dòng Boot đó.

Bảng tham chiếu dưới đây phản ánh thông tin công bố tại ngày 24/11/2026:

| Spring Cloud Release Train | Spring Boot tương thích | Ghi chú |
|---|---|---|
| `2026.0.0` (Paddington) | `4.2.0` | GA ngày 20/11/2026; bản phát hành đầu tiên của train này dựa trên Spring Boot 4.2.0 |
| `2025.1.x` (Oakwood) | `4.0.x`; `4.1.x` từ `2025.1.2` | Phù hợp với dự án đang dùng Boot 4.0 hoặc 4.1 |
| `2025.0.x` (Northfields) | `3.5.x` | Trang Spring Cloud hiện đánh dấu train này đã hết vòng đời hỗ trợ cộng đồng |
| `2024.0.x` (Moorgate) | `3.4.x` | Trang Spring Cloud hiện đánh dấu train này đã hết vòng đời hỗ trợ cộng đồng |

Spring Cloud 2026.0.0 được công bố dựa trên Spring Boot 4.2.0. Trang Spring Cloud cũng nêu rõ quan hệ tương thích của các train 2025.1.x, 2025.0.x và 2024.0.x. Các train có dấu sao trên trang dự án đã đạt end of life; không nên chọn chúng cho một hệ thống mới nếu không có yêu cầu duy trì phiên bản cũ hoặc thỏa thuận hỗ trợ riêng.

Quy tắc chọn phiên bản:

1. Ghi nhận chính xác dòng Spring Boot hiện có, ví dụ `4.2.x`, `4.1.x` hoặc `3.5.x`.
2. Tra bảng Release Train tương thích trên trang Spring Cloud. Đừng suy luận tương thích chỉ từ số phiên bản gần nhau.
3. Chọn service release mới nhất trong train tương ứng. Service release thường chứa sửa lỗi và cập nhật tương thích trong cùng train.
4. Giữ nguyên cặp Boot/Cloud đã chọn trong toàn bộ service thuộc cùng bộ bài thực hành hoặc cùng hệ thống, trừ khi có kế hoạch nâng cấp được kiểm thử riêng.
5. Nếu dùng một train đã hết vòng đời, ghi nhận rõ lý do và kế hoạch nâng cấp. Không xem việc build thành công là bằng chứng phiên bản vẫn còn được hỗ trợ.

## 3. Chọn JDK phù hợp

JDK phải thỏa mãn yêu cầu của Spring Boot, các thư viện Spring Cloud và mọi thư viện bên thứ ba trong ứng dụng. Phiên bản Java tối thiểu của Boot chỉ là điều kiện đầu tiên; một driver, SDK hoặc plugin khác có thể yêu cầu JDK cao hơn.

Với Spring Boot 4.2.0, tài liệu System Requirements công bố:

- Java tối thiểu là 17; phiên bản tương thích được công bố đến Java 27.
- Maven 3.6.3 trở lên.
- Gradle 8.x từ 8.14 trở lên hoặc Gradle 9.x.

Đối với bài học và môi trường phát triển thông thường, JDK 21 LTS là lựa chọn cân bằng: cao hơn mức tối thiểu, được hỗ trợ bởi Boot 4.2.0 và thường có độ tương thích tốt với thư viện Java hiện hữu. JDK 25 cũng nằm trong dải tương thích Boot 4.2.0; có thể chọn nếu các dependency, plugin, CI và môi trường triển khai của dự án đã được xác nhận hỗ trợ. Không tự nâng JDK chỉ vì bản mới vừa phát hành.

Cần phân biệt ba phiên bản có thể khác nhau trên cùng một máy:

- JDK mà lệnh `java` tìm thấy qua `PATH`.
- JDK mà Maven hoặc Gradle dùng để chạy build.
- JDK toolchain mà compiler sử dụng để biên dịch source code.

Ví dụ, `java -version` có thể trả về Java 25 nhưng `mvn -v` lại cho thấy Maven đang chạy bằng Java 17 do `JAVA_HOME` trỏ đến một thư mục khác. IDE cũng có thể cấu hình một Project SDK riêng. Hãy kiểm tra cả các vị trí này để tránh tình trạng máy cá nhân build được nhưng CI hoặc container chạy thất bại.

Với Gradle, khai báo Java toolchain giúp build chọn đúng compiler:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Với Maven Spring Boot parent, có thể đặt phiên bản Java trong properties:

```xml
<properties>
    <java.version>21</java.version>
</properties>
```

Đặt phiên bản Java trong build không tự cài JDK. Máy build và máy chạy vẫn cần có JDK/JRE phù hợp, hoặc cấu hình toolchain/container tương ứng.

## 4. Cặp phiên bản đề xuất cho dự án mới

Với một dự án học service discovery bắt đầu tại thời điểm bài viết được cập nhật, có thể dùng cấu hình sau:

| Thành phần | Phiên bản ví dụ |
|---|---|
| JDK | 21 LTS |
| Spring Boot | `4.2.0` |
| Spring Cloud Release Train | `2026.0.0` |
| Maven | `3.6.3+` (nên dùng Maven Wrapper để cố định phiên bản build) |
| Gradle nếu chọn Gradle | `8.14+` hoặc `9.x` (nên dùng Gradle Wrapper) |

Đây là một bộ phiên bản có quan hệ tương thích được công bố. Khi Spring phát hành patch mới, hãy kiểm tra release notes và nâng cấp trong cùng train thay vì tự thay từng dependency Spring Cloud.

### Ví dụ Maven

Đoạn cấu hình cốt lõi cho `pom.xml` khi dùng Spring Boot 4.2.0:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

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
    <!-- REST API của service -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <!-- HTTP client được Eureka Client sử dụng -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-restclient</artifactId>
    </dependency>

    <!-- Không khai báo version riêng: Spring Cloud BOM quản lý -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Trong ví dụ này, Spring Boot parent quản lý dependency của Boot và Maven plugin; Spring Cloud BOM quản lý phiên bản Eureka Client cùng các module Spring Cloud liên quan. Tài liệu Spring Cloud Netflix hiện hành yêu cầu có một HTTP client được hỗ trợ trên classpath; ví dụ dùng `spring-boot-restclient`. Nếu ứng dụng chọn WebClient thì cần cấu hình dependency tương ứng theo tài liệu của phiên bản đang dùng.

### Ví dụ Gradle

Đoạn cấu hình tương đương cho `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

ext {
    set('springCloudVersion', '2026.0.0')
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-restclient'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
}
```

Không khai báo version cho từng starter Spring Cloud khi BOM đã quản lý. Nếu tự ghim một module Spring Cloud sang phiên bản khác train, dependency tree có thể chứa các module không được kiểm thử cùng nhau.

## 5. Tạo dự án bằng Spring Initializr

Với dự án mới, [Spring Initializr](https://start.spring.io/) là cách thuận tiện để tạo cấu hình ban đầu:

1. Chọn Maven hoặc Gradle và ngôn ngữ Java.
2. Chọn Spring Boot version phù hợp với Spring Cloud Release Train dự định dùng.
3. Chọn Java version mà Boot và các dependency hỗ trợ; ví dụ chọn 21.
4. Chọn dependency cần cho bài học, chẳng hạn Eureka Discovery Client hoặc Consul Discovery.
5. Generate project, mở file build và kiểm tra `spring-cloud-dependencies` đã được thêm đúng train.

Initializr có thể thêm BOM tương ứng khi chọn Spring Boot và các dự án Spring Cloud. Dù vậy, hãy đọc lại `pom.xml` hoặc `build.gradle` sau khi tải project: kiểm tra phiên bản Boot, Cloud BOM, Java và dependency đã chọn trước khi bắt đầu viết code.

## 6. Xác minh môi trường trước khi thêm logic discovery

Chạy các lệnh sau trong terminal tại thư mục dự án:

```bash
java -version
mvn -v
./mvnw -v
```

Với Gradle, kiểm tra JVM mà Gradle sử dụng:

```bash
./gradlew -version
```

Trên Windows, Maven Wrapper và Gradle Wrapper thường được gọi bằng `mvnw.cmd` và `gradlew.bat`.

Sau khi thêm dependency, xem cây dependency để xác nhận phiên bản đã được quản lý đồng bộ:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud
./mvnw clean verify
```

Hoặc với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean build
```

Kết quả cần xác nhận:

- Spring Boot starter và các module Boot thuộc cùng dòng version do Boot parent/plugin quản lý.
- Các module Spring Cloud, bao gồm Eureka hoặc Consul, đến từ cùng Release Train BOM.
- Không có version override thủ công khiến một module Spring Cloud lệch train.
- Build tool đang chạy trên JDK được hỗ trợ và compiler toolchain đúng phiên bản dự kiến.
- Build hoàn tất trước khi bắt đầu cấu hình địa chỉ registry hoặc viết mã gọi `DiscoveryClient`.

## 7. Xử lý các lỗi tương thích thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Startup báo `Spring Boot [...] is not compatible with this Spring Cloud release train` | Boot và Cloud Release Train không nằm trong cặp tương thích | Tra lại bảng tương thích, đổi về đúng train và dùng service release phù hợp |
| `NoSuchMethodError`, `NoClassDefFoundError` hoặc `ClassNotFoundException` sau khi thêm starter | Dependency bị lệch phiên bản, có BOM khác ghi đè hoặc khai báo version thủ công | Xem `dependency:tree`/`runtimeClasspath`, loại bỏ override không cần thiết và để BOM quản lý |
| `UnsupportedClassVersionError` khi chạy ứng dụng | Runtime JDK thấp hơn phiên bản Java dùng để biên dịch một class hoặc dependency | Nâng JDK runtime hoặc biên dịch về mức Java được toàn bộ môi trường hỗ trợ |
| Compiler báo không hỗ trợ `--release` hoặc source release đã chọn | JDK mà Maven/Gradle dùng để biên dịch thấp hơn cấu hình source/toolchain | Kiểm tra `mvn -v`, `gradle -version`, `JAVA_HOME` và Java toolchain |
| Máy cá nhân build được nhưng CI thất bại | JDK hoặc build tool trên CI khác local; wrapper chưa được dùng nhất quán | Commit Maven/Gradle Wrapper, cấu hình cùng JDK cho CI và kiểm tra lại toolchain |

Không tắt compatibility verifier chỉ để ứng dụng khởi động qua lỗi phiên bản. Cơ chế kiểm tra này giúp phát hiện một tổ hợp Boot/Cloud không được hỗ trợ; cần sửa nguyên nhân trong dependency management trước.

## 8. Quy trình chọn phiên bản cho dự án đang tồn tại

Nếu dự án đã có Spring Boot, không bắt đầu bằng việc nâng Spring Cloud lên bản mới nhất. Thực hiện theo thứ tự:

1. Đọc phiên bản Spring Boot trong `pom.xml` hoặc `build.gradle` và kiểm tra phiên bản thực tế bằng dependency tree.
2. Tra Release Train tương thích với đúng dòng Boot đó.
3. Kiểm tra trạng thái hỗ trợ của train và release notes, đặc biệt khi train đã cũ.
4. Chọn patch mới nhất trong train tương ứng và giữ nguyên BOM quản lý dependency.
5. Nếu cần chuyển major/minor Boot, lập thay đổi nâng cấp riêng: cập nhật JDK, Boot, Cloud train, plugin và các starter; sau đó chạy test/build và kiểm tra thay đổi migration.

Ví dụ, một ứng dụng Boot 4.1.x cần dùng Spring Cloud 2025.1.x từ 2025.1.2 trở lên. Ứng dụng Boot 3.5.x khớp với Spring Cloud 2025.0.x theo bảng tương thích, nhưng train này hiện đã được đánh dấu hết vòng đời hỗ trợ cộng đồng; nên có kế hoạch nâng cấp thay vì bắt đầu dự án mới trên train đó.

## 9. Checklist trước khi bắt đầu bài service discovery

- [ ] Đã xác định phiên bản Spring Boot chính xác.
- [ ] Đã tra bảng tương thích và chọn đúng Spring Cloud Release Train.
- [ ] Đã kiểm tra train còn được hỗ trợ hoặc có lý do rõ ràng để duy trì train cũ.
- [ ] JDK local, IDE, build tool, CI và runtime thống nhất với phiên bản Java mục tiêu.
- [ ] Maven/Gradle Wrapper được cấu hình để tái lập build.
- [ ] Spring Cloud BOM được import; các starter Spring Cloud không bị ghim version riêng.
- [ ] Dependency tree không có module Spring Cloud lệch train.
- [ ] Lệnh build hoàn tất trước khi cấu hình Eureka, Consul hoặc DiscoveryClient.

## Tài liệu tham khảo

- [Spring Cloud — Release Train và bảng tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 (Paddington) đã phát hành](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Boot 4.2.0 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot — Build Systems và dependency management](https://docs.spring.io/spring-boot/4.2-SNAPSHOT/reference/using/build-systems.html)
- [Spring Cloud Netflix — Eureka Client và HTTP client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Initializr](https://start.spring.io/)
