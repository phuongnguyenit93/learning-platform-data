# Quản lý dependency bằng BOM và tránh trộn phiên bản trong Spring Cloud Gateway

Khi xây dựng **Spring Cloud Gateway** làm điểm vào cho hệ thống microservices, các thư viện liên quan không hoạt động độc lập: Gateway dựa trên Spring Boot, Spring Framework, WebFlux, Reactor/Netty và có thể kết hợp Spring Cloud LoadBalancer, service discovery, Circuit Breaker, Spring Security. Chỉ cần một thư viện quan trọng lệch khỏi bộ phiên bản đã được kiểm thử chung, ứng dụng có thể biên dịch thành công nhưng lỗi khi khởi động hoặc khi xử lý request.

Bài học này tập trung vào **BOM (Bill of Materials)**, cách chọn một nhóm phiên bản tương thích và cách phát hiện, loại bỏ tình trạng trộn các phiên bản của Spring Cloud Gateway. Mục tiêu là giữ nền tảng ổn định trước khi cấu hình route predicate, filter chain, biến đổi đường dẫn/header, xác thực, giới hạn lưu lượng, retry, circuit breaker, TLS và quan sát lưu lượng.

## 1. Tại sao Gateway cần quản lý phiên bản đồng bộ?

Giả sử một Gateway sử dụng:

- Spring Boot để khởi động ứng dụng, tự động cấu hình và cung cấp hệ sinh thái Spring;
- Spring Cloud Gateway để định tuyến và chạy chuỗi filter;
- Spring WebFlux, Reactor và Reactor Netty để xử lý HTTP bất đồng bộ;
- Spring Cloud LoadBalancer hoặc discovery client để chuyển tiếp đến instance dịch vụ;
- Spring Cloud Circuit Breaker, Resilience4j, Spring Security và Micrometer tùy theo nhu cầu vận hành.

Các thành phần này gọi API của nhau ở cả thời điểm khởi động lẫn thời điểm chạy. Nếu dự án giữ Spring Cloud Gateway thuộc một release train cũ nhưng nâng riêng Spring Boot hoặc Reactor/Netty, một phương thức mà Gateway mong đợi có thể đã thay đổi chữ ký hoặc không còn tồn tại.

Một số biểu hiện thường gặp:

| Biểu hiện | Nguyên nhân liên quan đến dependency cần kiểm tra |
| --- | --- |
| `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` | Thư viện được biên dịch với API khác phiên bản thực tế trên classpath. |
| Lỗi khởi tạo bean/auto-configuration | Spring Boot, Spring Cloud hoặc starter không cùng nhóm tương thích. |
| Gateway khởi động nhưng route `lb://...` không tìm được instance | Thiếu LoadBalancer/discovery hoặc cấu hình discovery chưa đúng; đây **không nhất thiết** là lỗi phiên bản. |
| Lỗi khi dùng filter, circuit breaker, retry hoặc TLS | Cần phân biệt cấu hình nghiệp vụ với xung đột các thư viện Gateway, Spring Cloud, Reactor, Netty hay Resilience4j. |
| Maven/Gradle chọn phiên bản khác với dự kiến | Có khai báo version thủ công, BOM khác chồng lấp hoặc dependency kéo theo phiên bản bắc cầu (transitive dependency). |

Quy tắc quan trọng: **chọn phiên bản ở cấp nền tảng, sau đó để BOM quản lý phần lớn dependency thuộc nền tảng đó**.

## 2. BOM là gì và quản lý được những gì?

**BOM** là một POM có kiểu đóng gói `pom`, chứa tập quy tắc **dependency management** cho nhiều thư viện. Nó không tự thêm các thư viện đó vào ứng dụng; nó cung cấp phiên bản mặc định khi một dependency thực sự được khai báo hoặc được đưa vào cây phụ thuộc.

Đối với dự án Spring Cloud Gateway, cần phân biệt hai nhóm:

| Thành phần quản lý | Vai trò |
| --- | --- |
| **Spring Boot dependency management** (qua parent/BOM hoặc cấu hình Gradle tương đương) | Quản lý phần lớn phiên bản Spring Framework, Reactor, Netty, Jackson, Micrometer, Spring Security, thư viện test và các thư viện phổ biến mà Boot tích hợp. |
| **`org.springframework.cloud:spring-cloud-dependencies`** | BOM của một **Spring Cloud release train**, quản lý phiên bản tương thích của các dự án Spring Cloud, gồm Gateway, LoadBalancer, Circuit Breaker, discovery client và các thành phần Cloud liên quan. |

Ví dụ, khi khai báo `spring-cloud-starter-gateway` mà không có `<version>`, Maven dùng phiên bản do Spring Cloud BOM xác định. Phiên bản Reactor/Netty cần được để Spring Boot dependency management dẫn dắt, trừ khi tài liệu chính thức của bộ phát hành yêu cầu ngoại lệ cụ thể.

BOM giúp **căn chỉnh** phiên bản; nó không tự bảo đảm mọi tổ hợp sẽ tương thích. Version khai báo trực tiếp, plugin quản lý dependency khác, thứ tự/ưu tiên nhập BOM và cơ chế giải quyết xung đột của công cụ build vẫn có thể thay đổi phiên bản cuối cùng.

### Ba tầng cần kiểm tra

```text
Java runtime / toolchain
        |
        v
Spring Boot phiên bản X  -- quản lý Spring Framework, Reactor, Netty...
        |
        v
Spring Cloud release train Y -- quản lý Gateway, LoadBalancer, Circuit Breaker...
        |
        v
Các starter của ứng dụng -- không gắn version riêng nếu BOM đã quản lý
```

Không nên suy ra tương thích chỉ từ việc cả hai dependency đều mang số major gần nhau. **Phiên bản Spring Cloud dùng định danh release train** (chẳng hạn `2024.0.x`), trong khi Spring Boot dùng dạng `3.4.x`, và Gateway lại có số phiên bản dự án riêng (chẳng hạn `4.2.x`).

## 3. Chọn cặp Spring Boot và Spring Cloud trước khi viết dependency

Quy trình chọn phiên bản:

1. Xác định phiên bản Java có thể sử dụng trong môi trường build và production.
2. Chọn dòng Spring Boot đáp ứng yêu cầu dự án.
3. Tra **bảng tương thích chính thức của Spring Cloud** để chọn release train tương ứng.
4. Kiểm tra tài liệu Gateway của đúng release train đó: starter cho **WebFlux** hay **Server MVC**, tên artifact và các thay đổi cấu hình.
5. Chọn patch release được hỗ trợ trong cùng dòng; cập nhật theo một đợt có kiểm thử, không tự nâng riêng Gateway/Reactor/Netty.

Ví dụ về một tổ hợp cụ thể dùng **trong bài học**:

| Thành phần | Phiên bản ví dụ | Ghi chú |
| --- | --- | --- |
| Java | 17 | Mức nền tảng phù hợp với Spring Boot 3.x; dự án có thể chọn Java cao hơn nếu được hỗ trợ. |
| Spring Boot | `3.4.4` | Quản lý nhóm dependency nền tảng. |
| Spring Cloud | `2024.0.1` | Release train tương ứng với dòng Boot 3.4.x. |
| Spring Cloud Gateway | Để BOM quyết định | Không tự chèn `4.x.y` vào dependency starter. |

Đây là **ví dụ học cú pháp**, không phải lời khuyên sử dụng patch version này cho hệ thống mới. Khi bắt đầu dự án hoặc nâng cấp, hãy kiểm tra bảng tương thích, chính sách hỗ trợ và bản vá hiện hành trên [Spring Cloud release trains](https://spring.io/projects/spring-cloud) và [tài liệu Spring Cloud Gateway](https://docs.spring.io/spring-cloud-gateway/reference/).

**Lưu ý về biến thể:** trong ngữ cảnh release train của ví dụ, `spring-cloud-starter-gateway` là starter Gateway dựa trên **WebFlux**. Với release train mới hơn, tên starter có thể thay đổi hoặc phân biệt rõ hơn giữa **Gateway Server WebFlux** và **Gateway Server MVC**. Hãy chọn một biến thể theo tài liệu của phiên bản đang dùng; không thêm đồng thời starter WebFlux và Server MVC vì nghĩ rằng chúng là hai bản sao để dự phòng.

## 4. Cấu hình Maven: Spring Boot parent và Spring Cloud BOM

Ví dụ `pom.xml` tối giản cho Gateway WebFlux thuộc cặp phiên bản nêu trên:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>edge-gateway</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2024.0.1</spring-cloud.version>
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
            <artifactId>spring-cloud-starter-gateway</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Hãy quan sát các điểm sau:

- `spring-boot-starter-parent` quản lý phiên bản của nhiều dependency thuộc Spring Boot; plugin build cũng có cấu hình mặc định phù hợp.
- `spring-cloud-dependencies` được **import** trong `<dependencyManagement>`, với `<type>pom</type>` và `<scope>import</scope>`. Đây là cơ chế đưa bộ version vào dự án, **không** phải một thư viện chạy được đặt trong `<dependencies>`.
- Các Spring Cloud starter **không có** `<version>`; Spring Cloud BOM cung cấp phiên bản.
- `spring-cloud-starter-loadbalancer` chỉ bổ sung khả năng cân bằng tải phía client. Để URI `lb://service-name` hoạt động, ứng dụng còn cần nguồn danh sách service instance, ví dụ discovery client hoặc cấu hình instance phù hợp.

Nếu tổ chức dùng parent POM riêng thay vì `spring-boot-starter-parent`, vẫn cần bảo đảm dependency management của Spring Boot được nhập một cách đúng đắn và tương thích. Không giả định parent nội bộ tự động cung cấp cả hai BOM.

### Kiểm tra phiên bản Maven thực sự chọn

Chạy tại thư mục dự án có `pom.xml`:

```bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.cloud
```

Trên Windows có thể dùng `mvnw.cmd` tương ứng. `help:effective-pom` giúp xem cấu hình sau khi kế thừa và import BOM; `dependency:tree` cho biết dependency nào thực tế được đưa vào classpath. Nếu một thư viện có phiên bản lạ, hãy truy ra khai báo trực tiếp hoặc nhánh bắc cầu đưa nó vào.

## 5. Cấu hình Gradle: import Cloud BOM có chủ đích

Với Gradle Groovy DSL, một cách phổ biến là dùng Spring Boot plugin và `io.spring.dependency-management` để import Spring Cloud BOM:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.4'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2024.0.1')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở cấu hình này, dependency-management plugin kết hợp với Spring Boot plugin để quản lý các dependency của Boot; phần import khai báo release train cho Spring Cloud. Các starter không ghi version riêng.

Gradle cũng có cơ chế BOM gốc thông qua `platform(...)`; có thể dùng khi toàn bộ chiến lược version của dự án được thiết kế theo dependency constraints của Gradle. Tránh vừa dùng plugin, vừa thêm nhiều `platform`/`enforcedPlatform` và nhiều quy tắc `force` cho cùng nhóm thư viện khi chưa hiểu rõ ưu tiên: các cơ chế này có thể đưa ra kết quả phân giải khác với suy nghĩ ban đầu.

### Kiểm tra phiên bản Gradle thực sự chọn

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-gateway --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
```

`dependencies` cung cấp cây phụ thuộc; `dependencyInsight` giải thích tại sao một module cụ thể được chọn, bao gồm các ràng buộc hoặc xung đột phiên bản có liên quan. Trên Windows có thể chạy `gradlew.bat`.

## 6. Những kiểu trộn phiên bản thường gây lỗi

### 6.1. Ghi đè version của Gateway starter

**Không nên:**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
    <version>4.1.0</version>
</dependency>
```

Đoạn trên có thể tạo hỗn hợp không tương thích nếu release train hiện tại quản lý một phiên bản khác. Đây còn là cách đặt số phiên bản dễ nhầm: **starter** và **module lõi Gateway** không nhất thiết chia sẻ cùng quy ước đặt version như tên release train.

**Nên:**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
</dependency>
```

Đối với phụ thuộc do BOM quản lý, bỏ version và để công cụ build phân giải; sau đó xem dependency tree để xác nhận.

### 6.2. Nâng một mình Reactor, Netty hoặc Spring Framework

Ví dụ, thêm `reactor-netty-http` hoặc `spring-webflux` với version chỉ định để sửa một lỗi có thể vô tình thay đổi API/binary mà Gateway đang sử dụng. Các thư viện này thường do Spring Boot dependency management quản lý; nên ưu tiên nâng **patch release của Spring Boot tương thích**, đồng thời rà soát Spring Cloud BOM.

Khi buộc phải áp dụng một bản vá an ninh riêng trước lịch nâng cấp, cần lưu rõ lý do ngoại lệ, kiểm tra cây dependency, kiểm thử route/filter/TLS và kế hoạch trả lại quyền quản lý phiên bản cho BOM.

### 6.3. Trộn hai Spring Cloud release train

Một ứng dụng dùng Gateway theo release train A nhưng ép LoadBalancer hoặc Circuit Breaker theo release train B có thể phát sinh lỗi API dù mỗi thư viện tự chạy tốt ở dự án riêng.

**Cách sửa:** chọn đúng một Spring Cloud release train cho mỗi ứng dụng Gateway và để BOM đó quản lý các Spring Cloud dependency có mặt trong ứng dụng. Nếu có nhiều BOM nhập chồng lấp, kiểm tra effective POM hoặc kết quả dependency resolution để xác nhận quy tắc ưu tiên.

### 6.4. Trộn WebFlux và Server MVC

Gateway WebFlux dựa trên mô hình reactive; Gateway Server MVC dựa trên servlet stack. Việc thêm cả hai starter hoặc thêm `spring-boot-starter-web` vào Gateway WebFlux mà không có chủ đích có thể làm auto-configuration và hành vi HTTP lệch kỳ vọng.

**Cách sửa:** chọn biến thể Gateway theo kiến trúc ứng dụng; kiểm tra tên starter từ tài liệu đúng phiên bản, giữ các dependency web thống nhất với biến thể được chọn.

### 6.5. Lạm dụng version động, SNAPSHOT và override

Các dạng `+`, `latest.release`, `-SNAPSHOT`, `resolutionStrategy.force` hoặc khai báo version thủ công ở nhiều submodule làm build khó tái lập. Hai lần build cùng mã nguồn có thể kéo về tập thư viện khác nhau.

Với production, nên dùng release ổn định, khóa cặp Boot/Cloud ở vị trí quản lý tập trung, lưu lockfile nếu chiến lược build yêu cầu và chỉ nâng cấp qua thay đổi có review.

## 7. Quy trình xử lý xung đột phiên bản

Khi Gateway thất bại ở startup hoặc trong request đầu tiên, có thể dùng quy trình sau:

1. **Ghi lại hiện trạng:** phiên bản Java đang chạy, Spring Boot plugin/parent, Spring Cloud BOM, tên các Gateway starter, các dependency override và lỗi gốc đầu tiên trong stack trace.
2. **Kiểm tra tương thích:** đối chiếu cặp Boot/Cloud với tài liệu của release train. Một lỗi tương thích không nên được sửa bằng cách tắt cơ chế kiểm tra tương thích của Spring Cloud.
3. **Xem classpath thực tế:** dùng `dependency:tree` (Maven) hoặc `dependencyInsight` (Gradle) cho đúng thư viện bị nghi ngờ. Tìm đường đưa phiên bản không mong muốn vào ứng dụng.
4. **Loại bỏ override không cần thiết:** gỡ version trực tiếp của Spring Cloud starter và các dependency nền tảng đã được BOM quản lý. Sửa ở nơi quyết định phiên bản (parent/BOM/plugin), không vá rải rác ở từng submodule.
5. **Build và chạy lại:** kiểm tra ứng dụng khởi động; thử tối thiểu một route HTTP, predicate, filter biến đổi header/đường dẫn và các tính năng thực tế đang bật như `lb://`, circuit breaker, retry hoặc TLS.
6. **Kiểm chứng khi nâng cấp:** chạy test tích hợp có downstream service giả lập, kiểm tra mã trạng thái HTTP, header, timeout, retry và hành vi fallback. Quan sát log/metrics để phát hiện lỗi chỉ xuất hiện dưới tải.

Ví dụ tình huống:

> Một Gateway đang chạy ổn định được thêm filter circuit breaker. Người phát triển chèn phiên bản mới nhất của `spring-cloud-circuitbreaker-reactor-resilience4j` nhưng giữ nguyên BOM cũ. Khi khởi động, Gateway xuất hiện lỗi class/method ở thành phần Spring Cloud.
>
> Cách xử lý: trước tiên bỏ version riêng của thư viện Circuit Breaker, giữ dependency thuộc cùng release train, xem dependency tree và thử lại. Nếu tính năng bắt buộc chỉ có ở release train mới, nâng **cặp Spring Boot + Spring Cloud** theo bảng tương thích rồi chạy lại test route, filter và fallback.

## 8. Nâng cấp theo cặp và kiểm tra hồi quy

Để nâng Gateway từ một nhóm phiên bản sang nhóm mới:

| Giai đoạn | Việc cần làm | Kết quả mong đợi |
| --- | --- | --- |
| Chuẩn bị | Đọc compatibility matrix, release notes, yêu cầu Java và hướng dẫn migration của Gateway. | Xác định được cặp Boot/Cloud cùng biến thể Gateway đích. |
| Sửa build | Nâng Boot parent/plugin, Cloud BOM, plugin build khi cần; bỏ các version override lỗi thời. | BOM quản lý thống nhất phần lớn các dependency. |
| Xem dependency graph | Kiểm tra `runtimeClasspath`/Maven dependency tree, nhất là Spring, Reactor, Netty, Gateway, LoadBalancer, Security và Circuit Breaker. | Không còn phiên bản bị kéo lệch ngoài chủ đích. |
| Test chức năng | Kiểm tra route predicate, filter chain, rewrite path/header, auth, rate limit, retry, circuit breaker và service discovery đang sử dụng. | Hành vi request/response tương đương hoặc thay đổi có kiểm soát. |
| Test vận hành | Thử TLS, timeout, kết nối lỗi, log/tracing/metrics và tải thực tế. | Có căn cứ để triển khai, quan sát và rollback khi cần. |

Một bộ smoke test tối thiểu cho Gateway có thể bao gồm:

```text
GET /api/catalog/42
    -> route phù hợp predicate Path
    -> filter sửa/loại prefix và chuyển header theo cấu hình
    -> upstream nhận đúng path/header
    -> Gateway trả đúng status, body và tracing metadata

Upstream trả 5xx hoặc timeout
    -> retry/circuit breaker phản ứng theo đúng chính sách
    -> không nhân số lần gọi ngoài dự kiến
    -> log và metrics ghi nhận lỗi
```

Những test này không chứng minh toàn bộ dependency đều tương thích, nhưng phát hiện được nhiều lỗi thực tế mà kiểm tra `compile` không bao phủ.

## 9. Câu hỏi tự kiểm tra

**BOM có tự tải tất cả dependency của Gateway không?** Không. BOM khai báo quy tắc quản lý phiên bản; dependency chỉ tham gia classpath khi ứng dụng khai báo hoặc được một dependency khác kéo theo.

**Nếu đã dùng Spring Boot parent, có cần Spring Cloud BOM không?** Có khi sử dụng các Spring Cloud dependency và muốn quản lý chúng theo release train. Spring Boot parent và Spring Cloud BOM giải quyết hai nhóm dependency có liên quan nhưng khác vai trò.

**Ghi `<version>` trực tiếp cho starter có luôn gây lỗi không?** Không phải lúc nào cũng lỗi ngay, nhưng nó có thể vượt qua phiên bản mà BOM đã căn chỉnh và tạo rủi ro khi nâng cấp.

**Ứng dụng khởi động được có chứng minh BOM đúng không?** Chưa. Lỗi tương thích hoặc cấu hình có thể chỉ xuất hiện ở route, filter, `lb://`, kết nối TLS, retry hoặc trong điều kiện tải.

**Có nên tắt Spring Cloud Compatibility Verifier để chạy ứng dụng?** Không xem đó là cách khắc phục. Cần sửa cặp Boot/Cloud được hỗ trợ hoặc xác minh đầy đủ ngoại lệ có lý do kỹ thuật.

## Kết luận

Với Spring Cloud Gateway, **chọn cặp Spring Boot và Spring Cloud tương thích, nhập đúng BOM rồi để starter kế thừa version** là cách quản lý dependency an toàn và dễ bảo trì. Sau mỗi lần thay đổi, hãy kiểm tra cây dependency đã phân giải thực tế và chạy test xuyên qua route, filter, upstream cùng các tính năng vận hành quan trọng. BOM giúp giảm nguy cơ trộn phiên bản; kiểm thử và quan sát thực tế mới xác nhận Gateway hoạt động đúng trong hệ thống microservices.
