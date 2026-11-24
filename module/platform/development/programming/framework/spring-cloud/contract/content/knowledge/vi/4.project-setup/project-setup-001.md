# Chọn Spring Boot và Spring Cloud Release Train tương thích

## 1. Mục tiêu và vấn đề cần giải quyết

**Spring Cloud Contract (SCC)** hỗ trợ kiểm thử hợp đồng giữa **producer** (dịch vụ cung cấp API hoặc phát thông điệp) và **consumer** (dịch vụ gọi API hoặc nhận thông điệp). Trong một dự án Spring Boot, ta có thể định nghĩa hành vi HTTP hoặc message bằng **Groovy DSL/YAML DSL**, sinh test phía producer, đóng gói stub, cho consumer chạy **Stub Runner**, và đưa các bước kiểm chứng vào CI để phát hiện thay đổi không tương thích.

Trước khi tạo contract đầu tiên, cần chọn **bộ phiên bản** có thể hoạt động cùng nhau. Nếu chỉ chọn Spring Boot mới nhất rồi thêm một phiên bản Spring Cloud Contract bất kỳ, dự án có thể lỗi ngay khi khởi động, không sinh được test, không chạy được plugin, hoặc sinh stub khác phiên bản thư viện mà consumer đang dùng.

Bài này trả lời câu hỏi: **Làm thế nào chọn Spring Boot, Spring Cloud Release Train và Spring Cloud Contract tương thích, khai báo chúng đúng cách và tự kiểm chứng lựa chọn đó?**

Sau bài học, bạn cần làm được các việc sau:

1. Phân biệt phiên bản **Spring Boot**, **Spring Cloud Release Train** và **Spring Cloud Contract**.
2. Đọc bảng tương thích và chính sách hỗ trợ trước khi chốt phiên bản.
3. Cấu hình BOM của Spring Cloud, dependency và build plugin cho Maven hoặc Gradle.
4. Kiểm tra dependency đã resolve, generated contract test và stub artifact.
5. Nhận biết lỗi do lệch phiên bản và lập kế hoạch nâng cấp có kiểm soát.

## 2. Ba tầng phiên bản phải hiểu đúng

| Tầng | Ví dụ tên hoặc tọa độ | Quyết định điều gì? | Cách quản lý |
|---|---|---|---|
| **Spring Boot** | `org.springframework.boot:spring-boot-starter-parent`, plugin `org.springframework.boot` | Nền tảng ứng dụng, Spring Framework, các starter, thư viện nền và yêu cầu Java/build tool | Chọn một phiên bản Boot cụ thể, thường qua parent hoặc plugin |
| **Spring Cloud Release Train** | `org.springframework.cloud:spring-cloud-dependencies` | Tập phiên bản Spring Cloud đã được phối hợp kiểm thử với một dòng Spring Boot | Import **BOM** đúng release train |
| **Spring Cloud Contract** | `spring-cloud-starter-contract-verifier`, `spring-cloud-starter-contract-stub-runner`, plugin SCC | DSL, sinh producer test, sinh/đọc stub và chạy Stub Runner | Dependency theo BOM; **build plugin có version riêng** |

**Release Train** là một **bộ phiên bản** của các dự án Spring Cloud được phát hành và kiểm thử cùng nhau, ví dụ định dạng tên `2025.0.x`. Nó không phải số phiên bản của Spring Boot hay Spring Cloud Contract. Spring Cloud Contract có số phiên bản module riêng, chẳng hạn dạng `4.x.y`, và thuộc về một release train phù hợp.

Một cấu hình đúng có thể hình dung như sau:

~~~mermaid
flowchart TD
    B["Spring Boot đã chọn"] --> C["Chọn Spring Cloud Release Train tương thích"]
    C --> D["Import spring-cloud-dependencies BOM"]
    D --> E["Contract Verifier / Stub Runner dependencies"]
    C --> F["Xác định phiên bản Contract build plugin tương ứng"]
    E --> G["Chạy generated producer test và consumer stub test"]
    F --> G
    B --> G
~~~

**BOM (Bill of Materials)** là cơ chế quản lý các phiên bản dependency đã được phối hợp. Import Spring Cloud BOM thường cho phép bạn khai báo các dependency Spring Cloud **không cần ghi version trên từng dependency**. Tuy nhiên, **Maven build plugin** không tự được định phiên bản bởi `dependencyManagement`; Gradle plugin cũng có cơ chế version riêng. Vì vậy, việc dùng đúng BOM nhưng dùng plugin SCC sai dòng vẫn có thể gây lỗi.

Ngoài ba tầng trên còn có **Java**, Maven/Gradle, phiên bản framework kiểm thử (JUnit, MockMvc, WebTestClient...) và các thành phần chuyển đổi lớn như `javax.*` sang `jakarta.*`. Chúng phải được xem là ràng buộc đầu vào khi chọn phiên bản, đặc biệt khi đi qua một major version của Spring Boot.

## 3. Chọn release train theo đúng thứ tự

Không nên bắt đầu bằng cách tùy ý thêm dependency và để công cụ build tự tìm một phiên bản “gần đúng”. Quy trình lựa chọn có kiểm chứng là:

**Bước 1 — Xác định Spring Boot đích.** Kiểm tra phiên bản ứng dụng đang dùng, Java runtime, Maven/Gradle, các thư viện quan trọng và yêu cầu vận hành. Với dự án mới, chọn dòng Boot còn được hỗ trợ trong vòng đời triển khai dự kiến; với dự án hiện hữu, xem xét phạm vi thay đổi nếu nâng Boot.

**Bước 2 — Tra bảng tương thích Spring Cloud ↔ Spring Boot từ nguồn chính thức.** Tại trang Spring Cloud và trang Supported Versions, tìm release train hỗ trợ **dòng Boot đang chọn**. Phải kiểm tra cả **khả năng tương thích kỹ thuật** lẫn **trạng thái hỗ trợ/bảo trì** tại thời điểm làm dự án.

**Bước 3 — Chốt bản vá cụ thể của cả hai bên.** Chọn phiên bản Boot patch và phiên bản Spring Cloud train patch có thực, tương thích với chính sách của nhóm. Ghi chúng vào cấu hình build, không chỉ viết “Boot 3.x” hoặc “Cloud 2025.x” trong tài liệu vận hành.

**Bước 4 — Xác định Spring Cloud Contract thuộc train đó.** Đọc BOM đã chọn hoặc release notes để xác nhận phiên bản thư viện SCC được quản lý. Với Maven/Gradle plugin của Contract, chọn plugin version cùng dòng/tương ứng với phiên bản verifier đã resolve. Không suy đoán phiên bản plugin chỉ từ số phiên bản Boot.

**Bước 5 — Chạy kiểm chứng thật.** Resolve dependencies, chạy ứng dụng hoặc slice test phù hợp, sinh producer test từ một contract tối thiểu, chạy test và đóng gói stub. Một bộ phiên bản chỉ được coi là đã xác minh cho dự án khi build thực tế thành công.

### Các ví dụ ánh xạ phiên bản thường gặp

| Spring Cloud Release Train | Dòng Spring Boot liên quan | Mục đích sử dụng thông tin |
|---|---|---|
| `2023.0.x` | `3.2.x`, `3.3.x` | Nhận diện một bộ phiên bản đời trước trong dự án đang bảo trì |
| `2024.0.x` | `3.4.x` | Ví dụ một cặp release train/Boot |
| `2025.0.x` | `3.5.x` | Ví dụ một cặp release train/Boot |

**Lưu ý về thời gian:** Bảng trên là **ví dụ về quan hệ các dòng phát hành đã biết**, không phải bảng “phiên bản mới nhất” hoặc cam kết rằng các dòng đó còn được hỗ trợ vào thời điểm bạn đọc. Spring Boot và Spring Cloud tiếp tục ra phiên bản mới; các release train cũ có thể hết thời gian hỗ trợ. Với Boot major mới hơn, phải tra **bảng tương thích hiện hành** thay vì ngoại suy từ số năm hay ép dùng train cũ.

Nguồn đối chiếu khi làm dự án:

- **Spring Cloud:** https://spring.io/projects/spring-cloud — trang dự án và liên kết đến release train.
- **Spring Cloud Supported Versions:** https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions — ma trận tương thích và vòng đời hỗ trợ.
- **Spring Boot:** https://spring.io/projects/spring-boot — phiên bản, tài liệu và yêu cầu môi trường.
- **Spring Cloud Contract Reference:** https://docs.spring.io/spring-cloud-contract/reference/ — cách tích hợp verifier, plugin và Stub Runner theo phiên bản tài liệu.

Nếu tài liệu của một phiên bản cũ khác với bảng tương thích hiện tại, hãy xác định rõ bạn đang kiểm tra **phiên bản lịch sử** hay **phiên bản đích**, đồng thời ưu tiên release notes và tài liệu tương ứng của từng dòng.

## 4. Ví dụ quyết định phiên bản có ghi nhận được

Giả sử một nhóm đang phát triển **inventory-service** (producer) và **checkout-service** (consumer), dùng Java 17 và muốn thử Spring Cloud Contract trong dòng Spring Boot 3.5.

Một tập phiên bản **minh họa để đọc cấu hình** là:

~~~text
Java runtime:                 17
Spring Boot:                  3.5.0
Spring Cloud Release Train:   2025.0.0
Spring Cloud Contract plugin: 4.3.0
~~~

Đây là **bộ phiên bản minh họa cho dòng 2025.0** trong bài, **không phải khuyến nghị rằng đó là patch mới nhất hoặc còn được hỗ trợ**. Trước khi sao chép vào dự án đang triển khai, cần tra bản vá hiện hành, kiểm tra phiên bản plugin có khớp với SCC được BOM quản lý, và thay bằng các bản vá được phê duyệt.

Nhóm nên ghi một bản quyết định ngắn:

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Java | Runtime và toolchain của CI có đạt tối thiểu mà Boot đích yêu cầu không? |
| Spring Boot | Dòng/patch đang chọn có được hỗ trợ trong thời gian vận hành không? |
| Spring Cloud | Release train được tài liệu chính thức xác nhận hỗ trợ Boot đích không? |
| Contract libraries | Version thực tế của verifier và Stub Runner được BOM quản lý là bao nhiêu? |
| Contract plugin | Version plugin có cùng dòng với thư viện Contract không? |
| Build | Maven/Gradle, JUnit, test base và DSL chạy được trên hệ thống hiện có không? |
| Artifacts | CI có build và cấp đúng stub version cho consumer không? |

Việc ghi nhận này đặc biệt hữu ích khi một PR nâng cấp nền tảng sau vài tháng, hoặc khi producer và consumer được nâng cấp lệch thời điểm.

## 5. Thiết lập Maven với Spring Cloud BOM

Trong Maven, một cách thường dùng là để **Spring Boot parent** quản lý các dependency nền tảng và import **Spring Cloud BOM** trong `dependencyManagement`. Các starter Spring Cloud được khai báo **không kèm version**; Maven sẽ resolve theo BOM.

Ví dụ `pom.xml` bên producer, dùng bộ phiên bản minh họa ở phần trước:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>inventory-service</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.0.0</spring-cloud.version>
        <!-- Kiểm tra version plugin với BOM trước khi áp dụng. -->
        <spring-cloud-contract.plugin.version>4.3.0</spring-cloud-contract.plugin.version>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-contract-verifier</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-contract-maven-plugin</artifactId>
                <version>${spring-cloud-contract.plugin.version}</version>
                <extensions>true</extensions>
                <configuration>
                    <baseClassForTests>com.example.inventory.ContractTestBase</baseClassForTests>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Hai giá trị cần đối chiếu khi nâng cấp:** `spring-cloud.version` và `spring-cloud-contract.plugin.version` nếu BOM mới đưa Contract sang dòng khác. Ví dụ đã khai báo mỗi giá trị một lần trong `properties` rồi tham chiếu lại ở BOM và plugin, tránh sao chép nhiều hằng số rồi quên cập nhật.

### Vì sao có cả BOM và version của Maven plugin?

Maven `dependencyManagement` quản lý **project dependencies**. Plugin `spring-cloud-contract-maven-plugin` nằm trong `build/plugins`, nên cần cấu hình version plugin theo cơ chế quản lý plugin. Spring Cloud BOM **không tự đảm bảo** version plugin được chọn đúng. Mặt khác, bạn thường **không cần** ghi version cho `spring-cloud-starter-contract-verifier` nếu BOM có quản lý dependency đó.

Nếu công ty đã dùng parent POM riêng, bạn vẫn có thể import Spring Cloud BOM trong `dependencyManagement`; không bắt buộc thay parent công ty bằng Spring Boot parent. Khi đó cần kiểm tra thêm cách parent hiện tại quản lý Boot dependencies, plugins và thứ tự ưu tiên BOM.

### Lớp cơ sở cho generated producer test

SCC cần biết test sinh ra sẽ gọi ứng dụng theo cách nào. Giá trị `baseClassForTests` trong ví dụ trỏ đến lớp test do bạn tạo dưới test sources, có thể chuẩn bị MockMvc, WebTestClient, RestAssured hoặc dữ liệu test. Ví dụ với **MockMvc và RestAssuredMockMvc** (khi các thư viện test phù hợp đã có trên classpath):

~~~java
package com.example.inventory;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
public abstract class ContractTestBase {

    @Autowired
    WebApplicationContext context;

    @BeforeEach
    void setupContractTests() {
        RestAssuredMockMvc.webAppContextSetup(context);
    }
}
~~~

Lớp cơ sở không định nghĩa contract; nó cung cấp **môi trường để generated test có thể chạy**. Cần chọn đúng test mode và các thư viện tương thích trong cấu hình plugin. Contract DSL sẽ nằm riêng, thường ở `src/test/resources/contracts/`.

## 6. Thiết lập Gradle với plugin và BOM

Trong Gradle, Spring Boot và Spring Cloud Contract thường được khai báo qua **plugins**, còn Spring Cloud BOM được import qua plugin `io.spring.dependency-management` hoặc cơ chế dependency platform được dự án lựa chọn.

Ví dụ **Groovy DSL**, `build.gradle`, cũng dùng bộ phiên bản minh họa:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'org.springframework.cloud.contract' version '4.3.0'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2025.0.0'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.example.inventory.ContractTestBase'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là ví dụ về **cách phối hợp cấu hình**, không phải lockfile cho một ứng dụng production. Với dự án đang dùng **Gradle Kotlin DSL**, version catalog, plugin management hoặc native Gradle platform, cú pháp và điểm đặt BOM sẽ khác; nguyên tắc vẫn là **một bộ phiên bản Boot–Cloud–Contract được quyết định và kiểm chứng thống nhất**.

Nếu không dùng plugin `io.spring.dependency-management`, cần chủ động khai báo `platform("org.springframework.cloud:spring-cloud-dependencies:<train-version>")` trong các configuration thích hợp. Không nên trộn nhiều cơ chế quản lý phiên bản mà chưa kiểm tra kết quả resolve thực tế.

### Lỗi hay gặp khi dùng Gradle

- Khai báo đúng `spring-cloud-dependencies` nhưng plugin `org.springframework.cloud.contract` lại thuộc dòng khác.
- Có BOM ở `implementation` nhưng thiếu ràng buộc phiên bản trên `testImplementation`, khiến dependency test resolve theo cấu hình khác kỳ vọng.
- Dùng `resolutionStrategy.force` hoặc version catalog để ép một thư viện Spring Cloud ra ngoài BOM mà không có lý do tương thích rõ ràng.
- Plugin Java hoặc Spring Boot không được áp dụng/không tương thích với phiên bản Gradle đang chạy.
- Toolchain Java 17 được khai báo nhưng runner CI không thể tải hoặc sử dụng JDK thích hợp.

## 7. Cấu hình consumer: Stub Runner phải thuộc cùng hệ sinh thái

Producer sử dụng **Contract Verifier** để sinh và chạy test. Consumer sử dụng **Stub Runner** để tải và chạy stub producer, thường chỉ trong test scope.

Ví dụ bổ sung vào `pom.xml` của consumer khi dự án đã dùng Spring Cloud BOM tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

Hoặc trong Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}
~~~

Thông thường không đưa Stub Runner vào `implementation`/runtime production nếu chỉ phục vụ integration test. Producer và consumer **không bắt buộc có cùng mọi phiên bản thư viện ứng dụng**, nhưng mỗi bên cần bộ Boot–Cloud của chính nó tương thích; đồng thời định dạng/protocol của stub, tọa độ artifact và test phải tương thích với phía consumer.

Ví dụ producer build ra:

~~~text
com.example:inventory-service:1.1.0-rc1:stubs
~~~

Consumer cần biết chính xác **groupId, artifactId, version, classifier** của stub ứng viên để tránh dùng nhầm bản cũ. Việc BOM đúng chỉ giải quyết nền tảng thư viện; nó không tự xác nhận consumer đã lấy **đúng stub của commit ứng viên**.

## 8. Kiểm chứng bằng lệnh build: nhìn vào kết quả resolve

Sau khi chọn bộ phiên bản và khai báo dependency, bước tiếp theo là **quan sát thứ mà công cụ build thực sự tải về**. Đọc POM hoặc Gradle file thôi chưa đủ, vì parent, BOM, dependency bắc cầu và quy tắc override có thể làm thay đổi kết quả.

### Với Maven

Trên môi trường Unix/macOS dùng `./mvnw`; trên Windows có thể dùng `mvnw.cmd`. Các lệnh quan trọng:

~~~bash
# Kiểm tra phiên bản JDK và Maven Wrapper đang dùng.
./mvnw --version

# Xem POM hiệu lực sau khi gộp parent, BOM và cấu hình plugin.
./mvnw help:effective-pom

# Xem các phụ thuộc Spring Cloud đã thực sự resolve.
./mvnw dependency:tree -Dincludes=org.springframework.cloud

# Chạy vòng build/test liên quan đến Contract Verifier.
./mvnw clean verify
~~~

Khi đọc kết quả, cần xác nhận:

1. **Spring Boot** được lấy từ parent hoặc dependency management đúng phiên bản đã chọn.
2. Các dependency **Spring Cloud Contract** nằm trong dòng mà BOM dự định quản lý; tránh nhiều version SCC khác nhau do khai báo thủ công.
3. **Maven plugin** Contract đã chọn đúng version; tìm trong effective POM thay vì chỉ nhìn dependency tree.
4. **Generated contract tests** đã được tạo và được test runner chạy, thay vì một build xanh vì hoàn toàn không có contract.
5. Build không có lỗi classloading/NoSuchMethodError/NoClassDefFoundError, và controller/message handler được gọi đúng cách.

Đường dẫn generated sources phụ thuộc plugin và build configuration. Với Maven, thường có vùng generated contract tests trong `target/generated-test-sources/contracts/`. Hãy dựa vào log của plugin và thư mục output thực tế của dự án.

### Với Gradle

~~~bash
# Kiểm tra Gradle và JVM đang dùng.
./gradlew --version

# Xem đồ thị phụ thuộc của test.
./gradlew dependencies --configuration testRuntimeClasspath

# Tìm dependency Spring Cloud Contract cụ thể và nguồn version được chọn.
./gradlew dependencyInsight --dependency spring-cloud-contract-verifier --configuration testRuntimeClasspath

# Xem các task do plugin Contract cung cấp.
./gradlew tasks --all

# Chạy test, bao gồm generated contract tests nếu cấu hình plugin đã nối đúng.
./gradlew clean test
~~~

Trên Windows có thể dùng `gradlew.bat`. Tên task và output cụ thể có thể thay đổi theo phiên bản plugin; hãy dùng danh sách task và log build để kiểm tra. **Không suy ra test Contract đã chạy chỉ vì lệnh test exit 0.**

## 9. Kiểm chứng tối thiểu: từ contract đến generated test

Có thể dùng một endpoint HTTP đơn giản để xác nhận nền tảng đã được chọn đúng, trước khi viết contract cho toàn bộ API.

Giả sử inventory-service hỗ trợ:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Response dự kiến:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Tệp Groovy DSL minh họa tại `src/test/resources/contracts/inventory/shouldReturnStock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Trả tồn kho để checkout quyết định đặt hàng'
    request {
        method GET()
        url '/api/inventory/SKU-123'
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

Một dự án dùng **YAML DSL** có thể diễn đạt cùng hành vi bằng YAML, thay vì Groovy:

~~~yaml
description: Trả tồn kho để checkout quyết định đặt hàng
request:
  method: GET
  url: /api/inventory/SKU-123
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

Để phép kiểm chứng có ý nghĩa, producer phải **thực sự triển khai endpoint** và lớp test base phải đưa generated test đến đúng ứng dụng. Khi chạy Maven `verify` hoặc Gradle `test`, hãy tìm generated test chứa assertion về status/body và kết quả test đó. Nếu chưa có implementation, test được mong đợi sẽ đỏ; đó là bằng chứng plugin và test runner đang hoạt động, **không phải lỗi tương thích phiên bản**.

Sau khi test producer đạt, build có thể tạo **stub artifact**. Lệnh đóng gói/phát hành stub phụ thuộc plugin và pipeline; khi kiểm tra local, cần xác nhận artifact `stubs` xuất hiện với tọa độ đúng. Consumer dùng Stub Runner trỏ tới artifact này để kiểm tra hành vi gọi API hoặc nhận message theo contract.

### Khi kiểm thử hợp đồng message

Với Kafka, RabbitMQ hoặc Spring Cloud Stream, cùng quy trình version vẫn áp dụng: chọn Boot–Cloud–Contract tương thích, cấu hình messaging adapter/test binder tương ứng, viết contract input/output message và chạy generated verification. Riêng messaging phải kiểm tra cả phiên bản serialization, header, topic/destination và test infrastructure; việc SCC plugin chạy được chưa đủ để kết luận broker production đã được kiểm chứng.

## 10. Spring Cloud Compatibility Verifier và lỗi lệch version

Một số cấu hình Spring Cloud có **Compatibility Verifier** kiểm tra dòng Spring Boot được chạy với release train Spring Cloud. Khi sai, ứng dụng có thể báo lỗi khởi động theo dạng:

~~~text
Spring Boot [X] is not compatible with this Spring Cloud release train
~~~

Thông báo có thể gợi ý những dòng Boot được hỗ trợ. Đây là tín hiệu cấu hình cần được xử lý, không nên xem như lỗi ngẫu nhiên của máy phát triển.

Ví dụ, nếu ứng dụng đã chuyển sang Boot 3.5.x nhưng vẫn import release train dành cho Boot 3.4.x, dependency có thể resolve thành công, song ứng dụng không khởi động hoặc lỗi API khi chạy test. **Cách sửa đúng** là chọn lại một cặp Boot–Cloud nằm trong ma trận tương thích rồi cập nhật Contract plugin tương ứng.

Một số hướng dẫn trên Internet đề cập việc tắt kiểm tra bằng cấu hình:

~~~properties
spring.cloud.compatibility-verifier.enabled=false
~~~

Đây **không phải cách sửa tương thích**. Tắt verifier chỉ bỏ qua một cổng kiểm tra, không thay đổi classpath, API hay khả năng vận hành của các thư viện. Không dùng cách này để “làm xanh CI” khi chưa xác nhận nguyên nhân và tính tương thích của bộ phiên bản.

## 11. Các lỗi lựa chọn phiên bản và cách chẩn đoán

| Dấu hiệu | Nguyên nhân đáng xem xét | Kiểm tra/xử lý |
|---|---|---|
| Ứng dụng báo Boot không tương thích Cloud train | Chọn sai cặp Boot–Cloud | Xem bảng Supported Versions, đổi release train hoặc Boot cho đúng |
| `NoSuchMethodError` / `NoClassDefFoundError` khi chạy generated test | Lệch phiên bản thư viện Spring/Contract, override dependency hoặc plugin không khớp | Xem dependency tree/insight, effective POM, plugin version |
| Build xanh nhưng không có generated contract test | Chưa bật plugin, đặt DSL sai vị trí, build không chạy lifecycle/task cần thiết | Xem plugin task, log generate test và source output |
| Maven dùng Contract verifier một version nhưng plugin version khác | BOM chỉ quản lý dependencies, plugin bị ghim riêng | Căn chỉnh version plugin với dòng Contract thực tế |
| Gradle resolve test dependencies ngoài BOM | BOM chỉ áp dụng một số configuration, version catalog/force ghi đè | Kiểm tra `testRuntimeClasspath` bằng dependencyInsight |
| Biên dịch lỗi import `javax.*` hoặc `jakarta.*` | Thay đổi major Spring Boot/Framework và API namespace | Kiểm tra yêu cầu migration của dòng Boot mới |
| Build chạy trên máy lập trình nhưng thất bại trong CI | Khác Java/Gradle/Maven, Maven local cache, plugin repository hoặc profile | Ghim toolchain/wrapper, dùng môi trường build tái lập và kiểm tra log |
| Stub Runner không tải được artifact | Stub chưa phát hành/cài vào kho, classifier/version sai, mode LOCAL/REMOTE sai | Kiểm tra tọa độ artifact, nguồn repository, quyền truy cập và version ứng viên |
| Contract producer xanh nhưng consumer vẫn lỗi khi thay API | Contract mới hợp với producer nhưng phá nhu cầu consumer cũ | Chạy consumer test với stub **ứng viên**, cân nhắc mở rộng–chuyển đổi–thu hẹp API |

Đọc lỗi theo thứ tự **nền tảng → dependencies đã resolve → Contract plugin → generated test → stub artifact → consumer test** giúp tránh nhầm sự cố tương thích dependency với sự cố nội dung contract.

## 12. Nâng cấp Spring Boot và Spring Cloud Contract có kiểm soát

Khi nâng Spring Boot, không nên chỉ đổi một con số và hy vọng dependency cũ tiếp tục hoạt động. Một quy trình nâng cấp thực tế gồm:

1. **Ghi trạng thái xuất phát:** Boot version, Cloud train, Contract dependency/plugin, Java, build tool, test report và stub coordinate hiện tại.
2. **Chọn đích theo ma trận chính thức:** Kiểm tra support window, Java, build tool, các thay đổi lớn của Spring Framework và Contract.
3. **Nâng tập phiên bản đồng bộ trong cấu hình:** Cập nhật Boot, Cloud BOM, Contract plugin, các BOM/override liên quan. Không kết luận một trạng thái trung gian sai ma trận là an toàn.
4. **Kiểm tra dependency đã resolve:** Loại bỏ version pin không cần thiết, phát hiện các dòng SCC trùng/khác nhau trên classpath.
5. **Chạy producer verification:** Compile, generated contract tests, unit/integration tests, smoke test khởi động.
6. **Đóng gói stub từ commit nâng cấp:** Gắn version ứng viên, bảo đảm stub phản ánh contract và implementation đã kiểm thử.
7. **Chạy consumer verification với stub ứng viên:** Bao phủ consumer hiện có, kể cả những phiên bản được hỗ trợ đang triển khai.
8. **Ghi kết quả và quyết định rollout:** Nếu contract thay đổi không tương thích, cần kế hoạch migration/versioning và thứ tự triển khai phù hợp.

Nếu chỉ nâng patch trong cùng release train, phạm vi thay đổi thường nhỏ hơn một lần nâng major Boot, nhưng vẫn cần chạy lại các kiểm chứng quan trọng. Một bản patch có thể sửa bug hoặc thay đổi behavior mà test hiện có chưa bao phủ.

### Ví dụ đường đi nâng cấp

Một hệ thống giả định đang ở `Spring Boot 3.4.x + Spring Cloud 2024.0.x` muốn lên dòng Boot 3.5. Nhóm không chỉ đổi `3.4.x` thành `3.5.x`; cần lựa chọn train `2025.0.x` tương ứng, xem version Contract mà train mới quản lý, cập nhật version plugin, rồi kiểm chứng cả producer lẫn consumer bằng stub mới. Quyết định bản patch cụ thể vẫn dựa trên tài liệu và chính sách hỗ trợ tại thời điểm nâng cấp.

## 13. Đưa lựa chọn phiên bản vào CI/CD

Một bài demo trên máy cá nhân chưa đảm bảo tính lặp lại trong pipeline. Với Spring Cloud Contract, hãy ghi lại đầy đủ công cụ và artifact:

~~~mermaid
flowchart TD
    A["Chốt JDK + Boot + Cloud train + Contract plugin"] --> B["CI resolve dependencies và compile"]
    B --> C["Sinh và chạy producer contract tests"]
    C --> D{"Tests đạt?"}
    D -- "Không" --> E["Chặn thay đổi, phân tích version/contract/code"]
    D -- "Có" --> F["Đóng gói stub gắn version/commit ứng viên"]
    F --> G["Consumer CI chạy Stub Runner với đúng artifact"]
    G --> H{"Consumer tests đạt?"}
    H -- "Không" --> E
    H -- "Có" --> I["Qua cổng tương thích, tiếp tục quy trình release"]
~~~

Một pipeline phù hợp cần:

- Dùng cùng **JDK/toolchain**, Maven/Gradle Wrapper và các biến version đã xác nhận.
- Resolve dependency từ repository được cấu hình rõ ràng; kiểm soát snapshot hoặc version động.
- Chạy **generated tests** thật, không chỉ lệnh build thành công mà không có contract.
- Đóng gói stub và lưu thông tin **version, commit SHA, classifier, repository**.
- Cho consumer kiểm tra với **stub ứng viên**, tránh lấy nhầm stub production hoặc cache cũ.
- Báo lỗi rõ ràng khi không tìm thấy artifact; không coi “skip test” là hợp lệ.
- Có chính sách chặn merge/release khi producer test hoặc consumer compatibility gate thất bại.

**Lưu ý:** Cặp Boot–Cloud đúng là điều kiện cần để công cụ kiểm thử hoạt động, không phải bằng chứng API tương thích. Phát hiện breaking change vẫn phụ thuộc vào contract được mô tả đủ và consumer test thực sự dùng stub ứng viên.

## 14. Bài thực hành: chốt và kiểm chứng bộ phiên bản

**Bối cảnh:** Inventory Service cung cấp `GET /api/inventory/{sku}`. Checkout Service gọi endpoint này để quyết định nhận đơn hàng. Hai dịch vụ cần thiết lập Spring Cloud Contract để kiểm chứng hành vi.

**Nhiệm vụ 1 — Chọn phiên bản**

- Tra tài liệu chính thức, chọn một Spring Boot patch còn được hỗ trợ theo yêu cầu dự án.
- Tìm đúng Spring Cloud release train; ghi lại lý do và đường dẫn tài liệu.
- Xác định version SCC được BOM quản lý và version Maven/Gradle plugin tương ứng.
- Kiểm tra Java và build tool trong môi trường phát triển/CI.

**Nhiệm vụ 2 — Cấu hình producer**

- Tạo project Boot Web, import Spring Cloud BOM, thêm Contract Verifier trong test scope.
- Áp dụng Contract Maven/Gradle plugin với version phù hợp và cấu hình test base.
- Tạo một contract HTTP Groovy hoặc YAML thể hiện response của endpoint tồn kho.

**Nhiệm vụ 3 — Kiểm chứng build**

- Chạy lệnh xem dependency đã resolve.
- Chạy build để sinh và thực thi producer contract test.
- Nếu test đỏ, phân loại lỗi: cấu hình version/plugin, thiếu implementation, sai test base hay contract sai kỳ vọng.
- Xác nhận stub artifact được tạo ra với coordinate có thể truy vết.

**Nhiệm vụ 4 — Nối consumer**

- Thêm Stub Runner test dependency theo BOM của consumer.
- Cấu hình consumer test trỏ vào **stub của producer ứng viên**.
- Chạy test client thực của Checkout và assert dữ liệu tồn kho đã được đọc đúng.
- Mô phỏng đổi tên trường JSON, quan sát bước kiểm chứng nào phát hiện lỗi.

**Đầu ra nộp bài:** bảng quyết định version; phần cấu hình BOM và plugin; log dependency/version đã resolve; tên generated test và kết quả; tên artifact stub; kết quả consumer test; một đoạn giải thích vì sao cặp Boot–Cloud đã chọn phù hợp.

## 15. Checklist trước khi bắt đầu viết contract

- [ ] Đã chọn một bản **Spring Boot cụ thể**, biết yêu cầu Java/build tool.
- [ ] **Spring Cloud Release Train** nằm trong ma trận chính thức hỗ trợ dòng Boot đó.
- [ ] Đã kiểm tra **trạng thái hỗ trợ** và patch phù hợp thay vì chỉ chọn theo số lớn nhất.
- [ ] Đã import đúng **Spring Cloud BOM**, không ghi đè vô cớ từng dependency Contract.
- [ ] **Contract build plugin** được ghim phiên bản tương ứng với thư viện Contract đã resolve.
- [ ] `spring-cloud-starter-contract-verifier` nằm trong test scope phía producer.
- [ ] `spring-cloud-starter-contract-stub-runner` nằm trong test scope phía consumer nếu có test stub.
- [ ] Build thực sự **sinh và chạy** generated producer test với ứng dụng đúng ngữ cảnh.
- [ ] CI có cơ chế xuất bản/lấy **stub ứng viên** đúng version, commit và classifier.
- [ ] Có bước chạy consumer test với stub ứng viên trước khi quyết định phát hành.

## 16. Câu hỏi tự kiểm tra

**1. Spring Cloud `2025.0.x` có phải phiên bản Spring Cloud Contract không?**

Không. Đây là **release train** của Spring Cloud. Spring Cloud Contract là một dự án nằm trong release train và có version module riêng; BOM của release train quản lý version thư viện tương ứng.

**2. Đã import Spring Cloud BOM thì có cần chỉ định version cho Maven Contract plugin?**

Có. Maven `dependencyManagement` quản lý dependency của project, còn `spring-cloud-contract-maven-plugin` là build plugin và cần được chọn phiên bản phù hợp.

**3. Lệnh Maven `verify` chạy thành công có đủ chứng minh Contract hoạt động không?**

Chưa đủ. Cần xác nhận plugin đã sinh **generated contract test** từ ít nhất một contract, test đó được runner thực thi, assert hành vi đúng và stub được đóng gói như kỳ vọng.

**4. Vì sao không nên tắt Spring Cloud Compatibility Verifier để xử lý lỗi mismatch?**

Vì thao tác ấy chỉ bỏ qua kiểm tra khởi động, không thay đổi dependency hay tính tương thích nhị phân của ứng dụng. Cần chọn đúng cặp Boot–Cloud và xác minh bằng build/test thực tế.

**5. Producer và consumer có nhất thiết dùng cùng version Spring Boot không?**

Không nhất thiết. Mỗi dịch vụ phải dùng bộ Boot–Cloud nội bộ tương thích; hợp đồng/stub và khả năng giải mã hoặc xử lý message/HTTP giữa hai dịch vụ mới quyết định tương thích giao tiếp. Consumer test phải dùng đúng stub phiên bản producer đang xét.

---

**Điểm cần nhớ:** Chọn phiên bản Spring Cloud Contract là chọn **cả một bộ**: Spring Boot phù hợp với Spring Cloud Release Train, thư viện Contract được quản lý bởi BOM và build plugin Contract được căn chỉnh tương ứng. Hãy xác nhận bằng **dependency tree, generated test, stub artifact và consumer test**; không chỉ dựa vào việc cấu hình trông hợp lệ.
