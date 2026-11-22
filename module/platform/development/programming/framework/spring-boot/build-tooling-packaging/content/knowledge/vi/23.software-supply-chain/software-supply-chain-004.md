# Sinh SBOM bằng công cụ tương thích như CycloneDX

## 1. SBOM là gì và vì sao cần tạo trong build pipeline?

**Software Bill of Materials (SBOM)** là bản kê có cấu trúc, ở định dạng máy đọc được, mô tả các thành phần phần mềm tạo nên một sản phẩm hoặc artifact. Một SBOM hữu ích thường ghi tên/version ứng dụng và thư viện, nhà cung cấp, package URL (PURL), quan hệ phụ thuộc, license và checksum khi dữ liệu có sẵn.

Hãy hình dung một Spring Boot service:

~~~text
catalog-service 1.0.0
├── application classes
├── Spring Boot
│   ├── Spring Framework
│   ├── Jackson
│   └── ...
├── logging libraries
└── other runtime dependencies
~~~

Khi có CVE mới trong một thư viện, đội phát triển và vận hành cần trả lời nhanh:

- Sản phẩm nào đang chứa package bị ảnh hưởng?
- Package được dùng trực tiếp hay kéo theo từ dependency bắc cầu?
- Phiên bản nào đang được triển khai?
- Package có nằm trong executable JAR, container image hay chỉ trong test/build classpath?
- Có bản vá hoặc phiên bản thay thế nào?
- SBOM có mô tả đúng artifact được phát hành không?

**SBOM giúp lập danh mục và truy vết thành phần.** Nó không tự chứng minh phần mềm an toàn, không tự phát hiện mọi lỗ hổng, cũng không chứng minh dependency thực sự được gọi trong runtime. Muốn quản lý rủi ro chuỗi cung ứng, cần kết hợp SBOM với vulnerability scanning, license review, provenance, signing, VEX và quy trình cập nhật.

Bài này hướng dẫn sinh SBOM cho dự án Java/Spring Boot bằng **CycloneDX**, tích hợp vào Maven/Gradle, nhúng SBOM vào executable JAR để Spring Boot Actuator có thể cung cấp, tạo SBOM từ container image bằng Syft hoặc Buildpacks, kiểm tra schema và quét CVE.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt SBOM của Maven dependency graph, executable JAR và container image.
2. Giải thích các trường quan trọng của CycloneDX: bomFormat, specVersion, metadata, components, dependencies, PURL và serial number.
3. Sinh CycloneDX JSON bằng CycloneDX Maven Plugin; chọn makeBom hay makeAggregateBom phù hợp.
4. Tích hợp plugin với Spring Boot 4.1.2 và Java 17, kiểm tra file META-INF/sbom/application.cdx.json bên trong JAR.
5. Dùng Spring Boot Actuator /actuator/sbom để truy xuất SBOM theo quyền truy cập được kiểm soát.
6. Biết cách dùng CycloneDX Gradle Plugin, Paketo SBOM và Syft để bao phủ cả dependency ứng dụng lẫn package trong image.
7. Validate SBOM, so sánh inventory với dependency graph, scan bằng Grype và gắn kết quả với image digest.
8. Thiết kế CI gate, lưu artifact SBOM và xử lý trường hợp thiếu dependency, sai scope hoặc schema không tương thích.

## 2. Chọn đúng phạm vi SBOM

Một lỗi phổ biến là tạo một file SBOM rồi mặc định nó mô tả mọi thứ được triển khai. Thực tế có nhiều lớp inventory:

| Loại SBOM | Công cụ phù hợp | Thành phần thường được mô tả | Giới hạn cần hiểu |
| --- | --- | --- | --- |
| **Project/dependency SBOM** | CycloneDX Maven/Gradle Plugin | Direct và transitive dependencies trong build model | Không tự bao gồm mọi package OS của container |
| **Executable JAR SBOM** | CycloneDX + Spring Boot packaging | Dependency inventory được nhúng vào ứng dụng | Không nhất thiết phản ánh mọi thành phần runtime bên ngoài JAR |
| **Container image SBOM** | Syft, Docker Scout, Buildpacks SBOM | OS packages, JRE, Java libraries và các package phát hiện được trong image | Kết quả phụ thuộc khả năng catalog của scanner |
| **Build-time SBOM** | CNB/Paketo build output | Tool/build dependencies và thành phần chỉ dùng khi build | Có thể không xuất hiện trong final runtime image |
| **Runtime inventory** | Runtime/host inventory tools | Thành phần có trên host hoặc đang chạy | Cần xác định rõ môi trường, thời điểm và cách thu thập |

**Ví dụ:** CycloneDX Maven Plugin đọc Maven project/dependency model. Nó hữu ích để biết thư viện Java nào được resolve. Nhưng nếu container còn cài CA certificates, shell utilities, font packages hoặc JRE từ run image, những package đó không nhất thiết có trong Maven SBOM. Scanner chạy trên image cuối có thể tìm thêm các thành phần ấy.

Một quy trình trưởng thành thường lưu **cả application SBOM và image SBOM**, sau đó gắn chúng với cùng release/version, source commit và image digest. Không gộp tùy tiện hai bản kê vì chúng có phạm vi và mục tiêu khác nhau.

## 3. CycloneDX và các trường dữ liệu chính

CycloneDX là chuẩn SBOM do OWASP phát triển, được công bố thành tiêu chuẩn Ecma International **ECMA-424**. Chuẩn hỗ trợ mô tả software components, services, dependency relationships, licenses, vulnerabilities, cryptographic assets và nhiều loại BOM khác. Các công cụ thường dùng JSON hoặc XML.

Ví dụ rút gọn về cấu trúc JSON:

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.6",
  "serialNumber": "urn:uuid:...",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "catalog-service",
      "version": "1.0.0"
    }
  },
  "components": [
    {
      "type": "library",
      "group": "org.springframework",
      "name": "spring-core",
      "version": "6.x",
      "purl": "pkg:maven/org.springframework/spring-core@6.x"
    }
  ],
  "dependencies": [
    {
      "ref": "pkg:maven/org.springframework/spring-core@6.x",
      "dependsOn": []
    }
  ]
}
~~~

Đây là **mẫu minh họa**, không phải SBOM được tạo từ một dự án thực tế. Version cụ thể và quan hệ phụ thuộc phải đến từ build đã resolve.

| Trường | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **bomFormat** | Định dạng BOM, ví dụ CycloneDX | Xác định parser phù hợp |
| **specVersion** | Phiên bản schema CycloneDX | Chọn validator/scanner tương thích |
| **serialNumber** | Định danh của một BOM document | Phân biệt các bản BOM |
| **version** | Revision của BOM document | Không nhầm với version ứng dụng |
| **metadata.component** | Sản phẩm mà BOM mô tả | Kiểm tra đúng artifact/name/version |
| **components** | Danh sách thành phần | Inventory package/library |
| **dependencies** | Quan hệ giữa các component | Hiểu dependency graph |
| **purl** | Package URL định danh package | Match package với advisory/database |
| **bom-ref** | Reference duy nhất cho component trong BOM | Liên kết component với dependency graph |
| **hashes** | Checksum của artifact khi có dữ liệu | Đối chiếu package bytes |
| **licenses** | License metadata khi được cung cấp | Hỗ trợ license compliance |
| **externalReferences** | Liên kết tới source, VCS, website hoặc tài liệu | Truy vết nguồn |

**Đừng giả định mọi component đều có đủ hash, license hoặc PURL.** Plugin chỉ có thể ghi dữ liệu mà build model/repository/tool cung cấp. Giá trị trống hoặc NOASSERTION không phải bằng chứng component không có license; nó có thể chỉ ra rằng dữ liệu chưa được xác định.

### Chọn phiên bản schema

Ví dụ bên dưới sử dụng CycloneDX Maven Plugin **2.9.3** và schema **1.6**, một cặp phát hành tương thích đã được công bố. CycloneDX 1.7 là schema mới hơn; hãy nâng plugin và schema cùng lúc sau khi registry, scanner, validator và hệ thống tiếp nhận SBOM hỗ trợ. Không đặt schemaVersion 1.7 cho plugin chỉ hỗ trợ 1.6.

Tài liệu: [CycloneDX Specification](https://cyclonedx.org/specification/overview/) · [ECMA-424](https://ecma-international.org/publications-and-standards/standards/ecma-424/) · [CycloneDX Maven Plugin](https://cyclonedx.github.io/cyclonedx-maven-plugin/).

## 4. Công cụ phù hợp cho từng giai đoạn

| Công cụ | Input chính | Output | Khi nên dùng |
| --- | --- | --- | --- |
| **CycloneDX Maven Plugin** | Maven POM và dependency resolution | CycloneDX XML/JSON | Dự án Maven, multi-module reactor |
| **CycloneDX Gradle Plugin** | Gradle configurations/dependency graph | CycloneDX SBOM | Dự án Gradle |
| **Spring Boot SBOM integration** | SBOM được tạo trong build | SBOM trong JAR/WAR và Actuator endpoint | Cần lưu SBOM cạnh executable artifact |
| **Syft** | Container image, directory, archive, filesystem | CycloneDX, SPDX, Syft JSON | Inventory image cuối và OS packages |
| **Paketo/CNB SBOM** | Các buildpack đóng góp vào image | Syft, SPDX, CycloneDX theo buildpack support | Image tạo từ Cloud Native Buildpacks |
| **CycloneDX CLI** | CycloneDX BOM | Validate, diff, merge, convert, sign/verify | QA và quản lý BOM |
| **Grype** | Image hoặc SBOM | Vulnerability findings | Đối chiếu package với vulnerability database |

Không nhất thiết dùng tất cả công cụ. Chọn tối thiểu một công cụ tạo application SBOM và một bước kiểm tra inventory của **đúng artifact được phát hành**. Nếu container có package hệ điều hành/JRE do builder cung cấp, thêm image-level SBOM.

## 5. Maven + Spring Boot 4.1.2 + Java 17: ví dụ hoàn chỉnh

Spring Boot có tích hợp với CycloneDX Maven Plugin. Khi dùng spring-boot-starter-parent, parent POM đã cung cấp cấu hình plugin phù hợp. Để kích hoạt việc sinh SBOM, khai báo plugin trong build/plugins của project.

### 5.1. Cấu trúc thư mục

~~~text
sbom-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/dev/example/sbom/
        │   └── SbomDemoApplication.java
        └── resources/
            └── application.properties
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>sbom-demo</artifactId>
    <version>1.0.0</version>
    <name>sbom-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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
            </plugin>
            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao POM không ghi version CycloneDX plugin?** Ví dụ đang dùng Spring Boot starter parent, nơi Spring Boot quản lý version và cấu hình plugin cho SBOM. Parent cũng cấu hình để SBOM được tạo ở vị trí ứng dụng có thể đóng vào JAR. Nếu project dùng corporate parent hoặc chỉ import BOM spring-boot-dependencies, bạn phải quản lý plugin version/execution/output path rõ ràng như mục 7.

### 5.3. SbomDemoApplication.java

Tệp src/main/java/dev/example/sbom/SbomDemoApplication.java:

~~~java
package dev.example.sbom;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SbomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SbomDemoApplication.class, args);
    }

    @GetMapping("/api/status")
    public String status() {
        return "SBOM_DEMO_OK";
    }
}
~~~

Endpoint /api/status chỉ để xác nhận executable JAR vẫn chạy. Nó không tạo hoặc tính SBOM trong runtime; CycloneDX plugin đã tạo SBOM trong quá trình build.

### 5.4. application.properties

Tệp src/main/resources/application.properties:

~~~properties
spring.application.name=sbom-demo
server.port=8080

management.endpoints.web.exposure.include=health,sbom
management.endpoint.sbom.access=read-only
~~~

Endpoint sbom được expose qua HTTP để phục vụ bài thực hành. Trong production, cần bảo vệ bằng Spring Security, network policy hoặc management port riêng. SBOM có thể tiết lộ tên/version thư viện và cấu trúc dependency; **không mở endpoint này công khai**.

### 5.5. Build và tìm SBOM

Tại thư mục có pom.xml:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Với cấu hình Spring Boot parent, SBOM ứng dụng được tạo trong:

~~~text
target/classes/META-INF/sbom/application.cdx.json
~~~

Spring Boot executable JAR chứa resource này dưới classpath của ứng dụng:

~~~text
BOOT-INF/classes/META-INF/sbom/application.cdx.json
~~~

Kiểm tra file trong output classes:

~~~bash
test -s target/classes/META-INF/sbom/application.cdx.json
~~~

Kiểm tra entry trong executable JAR:

~~~bash
jar tf target/sbom-demo-1.0.0.jar | grep 'META-INF/sbom/application.cdx.json'
~~~

**Kết quả mong đợi:** có một entry kết thúc bằng:

~~~text
BOOT-INF/classes/META-INF/sbom/application.cdx.json
~~~

Nếu chỉ thấy SBOM ở target/bom.json nhưng không thấy trong JAR, bạn đã tạo được project SBOM nhưng chưa cấu hình resource được đóng vào executable archive. Đó là hai mục tiêu khác nhau.

### 5.6. Kiểm tra nội dung bằng jq

~~~bash
jq '{
  bomFormat,
  specVersion,
  serialNumber,
  application: .metadata.component,
  componentCount: (.components | length),
  dependencyEdges: (.dependencies | length)
}' target/classes/META-INF/sbom/application.cdx.json
~~~

Các giá trị thực tế phụ thuộc dependency graph và phiên bản plugin. Không ghi cứng component count hoặc một danh sách thư viện dự kiến nếu chưa đọc SBOM vừa sinh.

### 5.7. Chạy ứng dụng và xác nhận runtime

~~~bash
java -jar target/sbom-demo-1.0.0.jar
~~~

Ở terminal khác:

~~~bash
curl -fsS http://127.0.0.1:8080/api/status
~~~

**HTTP response body chính xác:**

~~~text
SBOM_DEMO_OK
~~~

Sau kiểm tra, dừng ứng dụng bằng Ctrl+C.

## 6. Truy xuất SBOM bằng Spring Boot Actuator

Spring Boot Actuator có sbom endpoint để đọc các SBOM có sẵn trên classpath. Khi plugin đã đóng CycloneDX vào executable JAR, Actuator có thể tự phát hiện SBOM có tên application.

### 6.1. Liệt kê SBOM

Khi ứng dụng chạy:

~~~bash
curl -i http://127.0.0.1:8080/actuator/sbom
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{
  "ids": [
    "application"
  ]
}
~~~

### 6.2. Tải SBOM ứng dụng

~~~bash
curl -fsS http://127.0.0.1:8080/actuator/sbom/application \
  -o target/actuator-application.cdx.json
~~~

Response có media type CycloneDX JSON, thường là:

~~~text
application/vnd.cyclonedx+json
~~~

Có thể xem một phần nội dung:

~~~bash
jq '{bomFormat, specVersion, application: .metadata.component}' \
  target/actuator-application.cdx.json
~~~

Actuator trả lại resource đã được build vào ứng dụng; nó không tự resolve dependency mới hoặc scan container mỗi khi nhận request.

### 6.3. Thêm SBOM khác

Actuator có thể expose nhiều SBOM. Ví dụ, nếu có một file SPDX ở vị trí /system.spdx.json:

~~~properties
management.endpoint.sbom.additional.system.location=optional:file:/system.spdx.json
management.endpoint.sbom.additional.system.media-type=application/spdx+json
~~~

Khi file tồn tại và cấu hình phù hợp, endpoint có thể liệt kê ID system. Tiền tố optional: cho phép ứng dụng khởi động ngay cả khi file không có. Hãy quản lý vị trí file và quyền đọc phù hợp.

**Lưu ý bảo mật:** không dùng SBOM endpoint như một public information API. Giới hạn truy cập cho đội vận hành/security hoặc dùng management network được bảo vệ. Nếu chỉ cần gửi SBOM cho scanner, xuất file trong CI và lưu cùng release artifact có thể phù hợp hơn việc expose endpoint ở production.

## 7. Cấu hình CycloneDX Maven Plugin khi không dùng Spring Boot parent

Nếu project không kế thừa spring-boot-starter-parent, hoặc muốn chủ động chọn output path/format, có thể cấu hình plugin tường minh. Ví dụ sau tạo SBOM JSON và đặt resource vào target/classes để JAR đóng gói.

**Đây là fragment** trong build/plugins của POM; plugin version được pin ở 2.9.3 và schema 1.6.

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <id>generate-application-sbom</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
            <configuration>
                <projectType>application</projectType>
                <schemaVersion>1.6</schemaVersion>
                <outputFormat>json</outputFormat>
                <outputName>application.cdx</outputName>
                <outputDirectory>${project.build.outputDirectory}/META-INF/sbom</outputDirectory>
                <includeCompileScope>true</includeCompileScope>
                <includeProvidedScope>true</includeProvidedScope>
                <includeRuntimeScope>true</includeRuntimeScope>
                <includeSystemScope>true</includeSystemScope>
                <includeTestScope>false</includeTestScope>
                <includeBomSerialNumber>true</includeBomSerialNumber>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Sau mvn clean verify, output dự kiến:

~~~text
target/classes/META-INF/sbom/application.cdx.json
~~~

### Giải thích tham số

- makeBom tạo SBOM cho module Maven hiện tại. Nó phù hợp với project đơn hoặc khi muốn BOM riêng từng module.
- makeAggregateBom tạo aggregate BOM tại root cho toàn Maven reactor và có thể tạo BOM riêng cho các reactor modules.
- projectType=application mô tả component gốc là ứng dụng, không phải thư viện.
- schemaVersion=1.6 chọn schema mà plugin 2.9.3 hỗ trợ.
- outputFormat=json chỉ tạo JSON; all có thể tạo cả XML và JSON.
- outputName=application.cdx tạo tên file application.cdx.json.
- outputDirectory đưa SBOM vào resource output trước phase package để Maven JAR plugin có thể đóng vào archive.
- includeTestScope=false loại dependency chỉ dùng cho test theo mặc định phổ biến của application SBOM.
- includeProvidedScope và includeSystemScope cần được cân nhắc theo cách ứng dụng được triển khai. Nếu dependency được runtime platform cung cấp thay vì đóng vào artifact, hãy xác định rõ liệu BOM cần mô tả dependency đó hay chỉ package thực sự được ship.
- includeBomSerialNumber=true thêm serial number cho document.

**Cẩn trọng khi dùng Spring Boot starter parent:** parent đã có cấu hình CycloneDX riêng để tạo application.cdx.json trong META-INF/sbom. Nếu ghi đè output path/goal, hãy kiểm tra mvn help:effective-pom và dùng một execution ID riêng khi cần tùy biến. Nếu không, cấu hình được kế thừa có thể làm bạn ngạc nhiên vì output vẫn được ghi vào đường dẫn SBOM của Spring Boot.

### Kiểm tra cấu hình Maven thực tế

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn clean verify
~~~

Tìm cyclonedx-maven-plugin và kiểm tra goal, execution, version, output format, output name, output directory và các dependency scopes. Không suy ra cấu hình effective chỉ từ phần POM con.

## 8. Maven multi-module: chọn BOM theo phạm vi reactor

Với project:

~~~text
platform/
├── pom.xml
├── shared-core/
├── customer-api/
└── billing-service/
~~~

Có hai nhu cầu:

- **Một SBOM cho mỗi module:** dùng makeBom. Điều này giúp mỗi artifact có inventory riêng.
- **Một SBOM tổng hợp toàn reactor:** dùng makeAggregateBom. Đây là lựa chọn hữu ích khi release một hệ thống gồm nhiều module cùng build.

Ví dụ goal aggregate trong plugin execution:

~~~xml
<execution>
    <id>aggregate-reactor-sbom</id>
    <phase>prepare-package</phase>
    <goals>
        <goal>makeAggregateBom</goal>
    </goals>
</execution>
~~~

Với Spring Boot parent, kiểm tra cấu hình mặc định đã có aggregate goal hay chưa trước khi thêm execution thứ hai.

Chạy reactor:

~~~bash
mvn -pl billing-service -am clean verify
~~~

-am yêu cầu Maven xây cả các project cần thiết trong reactor. Khi chạy riêng module hoặc chỉ dùng dependency đã cài ở local repository, phạm vi aggregate có thể khác. Hãy tạo SBOM từ **cùng build command, profile và reactor membership** với release.

### Dependency scope và profiles

Maven plugin có các lựa chọn include/exclude scope. Mặc định phổ biến của plugin gồm compile, provided, runtime, system; test scope bị loại. Tuy nhiên, provided không đồng nghĩa luôn nằm trong executable JAR. Một số dependency chỉ có mặt trong môi trường application server hoặc được runtime platform cung cấp.

SBOM cho release nên được tạo với:

1. Maven profiles giống pipeline phát hành.
2. Dependency versions đã được resolve trong build.
3. Scope policy phù hợp artifact.
4. Các module thực sự thuộc release.
5. Không dùng một BOM từ build local khác profile làm bằng chứng cho production.

Không loại test dependencies khỏi mọi báo cáo một cách máy móc: một SBOM riêng cho build/test environment có thể hữu ích để đánh giá build supply chain. Hãy đặt tên và mục đích khác nhau cho **runtime/application BOM** và **build/test BOM**.

## 9. Gradle: CycloneDX Plugin và Spring Boot integration

Với Gradle, Spring Boot 4.1 có thể phối hợp với CycloneDX Gradle Plugin. Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'org.cyclonedx.bom' version '3.0.0'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}
~~~

Khi CycloneDX plugin được áp dụng, Spring Boot plugin cấu hình task cyclonedxBom theo mục đích application, JSON output application.cdx.json, không tạo XML và không nhúng full license text. Spring Boot cũng đưa SBOM vào JAR/WAR ở META-INF/sbom và thêm manifest headers Sbom-Format/Sbom-Location.

Chạy:

~~~bash
./gradlew cyclonedxBom bootJar
~~~

Kiểm tra:

~~~bash
jar tf build/libs/sbom-demo-1.0.0.jar
~~~

Trong archive cần có resource SBOM tại META-INF/sbom bên trong application classpath. Đường dẫn manifest và SBOM phải tương ứng nhau. Nếu Gradle plugin hoặc Spring Boot version thay đổi, hãy xem task configuration và output path thực tế.

**Gradle khác Maven:** không copy cấu hình XML của Maven sang build.gradle. Kiểm tra version Gradle plugin tương thích, dependency configurations được đưa vào BOM và task được chạy trước khi bootJar đóng gói.

## 10. Sinh SBOM cho container image

Application SBOM không mô tả đầy đủ mọi package trong final image. Nếu bạn đóng gói bằng Dockerfile hoặc Cloud Native Buildpacks, hãy tạo thêm **image-level SBOM**.

### 10.1. Dùng Syft quét image

Syft hỗ trợ catalog container images, directories và archives; có thể xuất CycloneDX JSON:

~~~bash
syft sbom-demo:1.0.0 -o cyclonedx-json=target/image.cdx.json
~~~

Với image từ registry, nên scan đúng immutable digest:

~~~bash
syft registry.example.com/team/sbom-demo@sha256:REPLACE_WITH_REAL_DIGEST \
  -o cyclonedx-json=target/image.cdx.json
~~~

Chuỗi REPLACE_WITH_REAL_DIGEST chỉ là placeholder cho lệnh minh họa; phải thay bằng digest thực tế từ registry trước khi chạy.

Image SBOM có thể bao gồm OS packages, JRE và các package Java mà scanner nhận diện được. Khả năng phát hiện phụ thuộc format/metadata của từng package. Đừng khẳng định scanner đã phát hiện tất cả chỉ vì lệnh exit code 0.

### 10.2. Dùng Docker Scout

Một lựa chọn khác nếu tổ chức dùng Docker Scout:

~~~bash
docker scout sbom sbom-demo:1.0.0
~~~

Lệnh này tạo/hiển thị SBOM cho image theo công cụ Docker Scout. Kiểm tra quyền truy cập, phiên bản CLI, cấu hình registry và định dạng export theo quy trình của tổ chức.

### 10.3. Buildpacks/Paketo có SBOM riêng

Paketo buildpacks có thể tạo SBOM ở các định dạng Syft JSON, SPDX JSON và CycloneDX JSON nếu buildpack hỗ trợ. Có thể tải SBOM của image:

~~~bash
pack sbom download sbom-demo:1.0.0 --output-dir target/paketo-sbom
~~~

Tìm các file JSON:

~~~bash
find target/paketo-sbom -type f -name "*.json"
~~~

**Điểm cần nhớ:** SBOM tải bằng pack sbom download tập trung vào các **launch-time app dependencies**. Nếu cần cả build-time dependencies, phải thu thập SBOM tại build time bằng pack build và tùy chọn --sbom-output-dir:

~~~bash
pack build sbom-demo:1.0.0 \
  --path target/sbom-demo-1.0.0.jar \
  --builder paketobuildpacks/builder-noble-java-tiny \
  --sbom-output-dir target/cnb-build-sbom
~~~

Lệnh trên là ví dụ với builder Paketo; chọn builder phù hợp Java version, architecture và policy. Buildpacks khác nhau có thể hỗ trợ SBOM formats khác nhau. Kiểm tra buildpack.toml và metadata của builder để biết format thực tế.

**Không nhầm ba loại file:** Maven CycloneDX SBOM mô tả dependency model; Paketo SBOM mô tả những gì buildpacks đóng góp; Syft image SBOM catalog final image. Chúng có thể bổ sung nhau nhưng không tự động tương đương.

## 11. Validate SBOM trước khi chuyển cho scanner

Một file JSON hợp lệ về cú pháp chưa chắc là CycloneDX BOM hợp lệ theo schema. Hãy kiểm tra định dạng và phiên bản schema.

### 11.1. Validate bằng CycloneDX CLI

Với plugin 2.9.3 và schema 1.6:

~~~bash
cyclonedx validate \
  --input-file target/classes/META-INF/sbom/application.cdx.json \
  --input-version v1_6 \
  --fail-on-errors
~~~

Kết quả thành công thường thông báo:

~~~text
BOM validated successfully.
~~~

Nếu file là SBOM từ image:

~~~bash
cyclonedx validate \
  --input-file target/image.cdx.json \
  --input-version v1_6 \
  --fail-on-errors
~~~

Hãy dùng input-version tương ứng với specVersion trong chính file. Nếu scanner/validator hỗ trợ schema mới hơn, nâng plugin và schema một cách đồng bộ.

### 11.2. Kiểm tra trường cốt lõi

~~~bash
jq '{
  format: .bomFormat,
  spec: .specVersion,
  subject: .metadata.component,
  components: (.components | length),
  dependencyNodes: (.dependencies | length)
}' target/classes/META-INF/sbom/application.cdx.json
~~~

Kiểm tra thủ công:

- bomFormat là CycloneDX.
- specVersion đúng phiên bản đã chọn.
- metadata.component mô tả đúng ứng dụng và version.
- components có dependencies kỳ vọng.
- dependencies phản ánh quan hệ package nếu plugin có dữ liệu.
- PURL/version không rỗng hoặc sai bất thường.
- License/hash có mặt khi nguồn dữ liệu cung cấp.
- Không có duplicate component references hoặc dependency edges hỏng.

### 11.3. Đối chiếu với Maven dependency tree

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Đối chiếu dependency tree với SBOM để nhận biết thiếu hoặc dư. Tuy nhiên, hai công cụ có mục đích và cách biểu diễn khác nhau; hãy so sánh theo package coordinates/version và scope, không chỉ số lượng component.

**Không dùng component count làm tiêu chí duy nhất.** Một BOM có 100 component chưa chắc đầy đủ hơn BOM có 90 component. Một BOM chứa nhiều test/build dependencies có thể kém phù hợp cho runtime release hơn một BOM đúng phạm vi.

## 12. Scan vulnerabilities từ SBOM

SBOM là đầu vào cho scanner. Ví dụ dùng Grype:

~~~bash
grype sbom:target/image.cdx.json
~~~

Hoặc scan trực tiếp image:

~~~bash
grype sbom-demo:1.0.0
~~~

Grype có thể đọc CycloneDX, SPDX và Syft formats. Trong CI, cần quản lý vulnerability database, thời điểm cập nhật và policy severity.

### Đọc kết quả scan

Khi có finding, xác minh:

1. Package URL/PURL, ecosystem, name và version.
2. CVE/advisory có áp dụng đúng phiên bản và build không.
3. Có bản vá hoặc phiên bản thay thế được hỗ trợ không.
4. Vulnerability nằm ở application dependency, JRE hay OS package.
5. Có VEX/exception đã được phê duyệt không.
6. Có thể rebuild/rebase/upgrade và regression test trong thời hạn policy không.

**Scan không phải phép chứng minh tuyệt đối.** Không có finding có thể do database chưa cập nhật, package không nhận diện được, CVE chưa được công bố hoặc scanner chưa hỗ trợ ecosystem. Một finding cũng cần xác minh phạm vi và applicability trước khi đưa ra kết luận.

## 13. Application SBOM và Image SBOM nên liên kết thế nào?

Một release có thể lưu cấu trúc:

~~~text
release/
├── sbom/
│   ├── application.cdx.json
│   └── image.cdx.json
├── scan/
│   └── grype-report.json
└── provenance/
    └── build-attestation.json
~~~

Các file trên cần liên kết với:

- Source commit SHA.
- Maven/Gradle version và JDK toolchain.
- Application version và checksum JAR.
- Container image reference và **digest thực tế**.
- Builder/run image hoặc Docker base image digest.
- SBOM schema version và generator version.
- Scan database version/time, policy result và exceptions đã duyệt.

Ví dụ metadata release:

~~~text
application = sbom-demo:1.0.0
source.commit = <full Git SHA>
jar.sha256 = <calculated JAR digest>
image.reference = registry.example.com/team/sbom-demo:1.0.0
image.digest = sha256:<actual registry digest>
application.sbom = application.cdx.json
image.sbom = image.cdx.json
scan.policy = <approved policy result>
~~~

Đây là **mẫu dữ liệu minh họa**, không phải digest hay attestation thật. Không gắn SBOM chỉ với mutable tag latest. Nếu image tag được push lại, digest có thể đổi; SBOM cũ sẽ không còn chắc chắn mô tả bytes hiện tại.

### Ký và lưu SBOM

CycloneDX CLI hỗ trợ signing/verification cho BOM; các hệ thống supply-chain attestation cũng có thể liên kết SBOM với artifact digest. Chọn cơ chế ký theo key management policy. Lưu public verification key, signing identity, provenance và thời điểm tạo cùng release metadata.

Không coi chữ ký SBOM là bằng chứng package không có lỗ hổng. Chữ ký chứng minh tài liệu được ký bởi một identity và không bị thay đổi sau khi ký; nội dung vẫn cần được kiểm tra.

## 14. CI/CD pipeline đề xuất

Một pipeline tối thiểu có thể đi theo thứ tự:

~~~text
Checkout commit
     |
Resolve dependencies with locked versions
     |
Compile + unit tests
     |
Generate CycloneDX application SBOM
     |
Package executable JAR (embed META-INF/sbom)
     |
Validate SBOM schema + inspect package scope
     |
Build OCI image
     |
Generate/collect image SBOM
     |
Vulnerability + license policy checks
     |
Publish image by digest + attach SBOM/provenance
     |
Deploy approved digest
~~~

| Gate | Điều kiện PASS | Khi FAIL |
| --- | --- | --- |
| **Generation** | SBOM file được tạo, không rỗng | Dừng release; kiểm tra plugin/task |
| **Identity** | Name/version đúng với artifact | Sửa build metadata và regenerate |
| **Schema** | Validator thành công với schema đã chọn | Kiểm tra format/schema/plugin compatibility |
| **Completeness** | Direct/transitive dependencies đúng scope | Đối chiếu dependency tree/profiles |
| **Packaging** | SBOM được nhúng trong JAR nếu policy yêu cầu | Sửa outputDirectory/lifecycle ordering |
| **Image inventory** | Image SBOM gắn đúng image digest | Scan lại image đã build/push |
| **Vulnerability** | Không vi phạm severity/exception policy | Patch, mitigate hoặc exception có phê duyệt |
| **License** | License policy được thỏa mãn hoặc có quyết định | Legal/security review |
| **Provenance** | SBOM liên kết đúng commit/JAR/image digest | Regenerate/re-attest đúng artifact |
| **Publication** | SBOM và scan report được lưu cùng release | Không deploy khi thiếu bằng chứng bắt buộc |

Ví dụ command trong pipeline Maven:

~~~bash
mvn -B -ntp clean verify
cyclonedx validate --input-file target/classes/META-INF/sbom/application.cdx.json --input-version v1_6 --fail-on-errors
jar tf target/sbom-demo-1.0.0.jar
syft sbom-demo:1.0.0 -o cyclonedx-json=target/image.cdx.json
grype sbom:target/image.cdx.json
~~~

Đây là các lệnh mẫu; CI cần xử lý exit codes, registry login, image digest và artifact upload theo platform cụ thể. Nếu build bằng Buildpacks, dùng cơ chế thu thập SBOM của builder hoặc scan final image.

## 15. Các giới hạn và điểm cần xem xét

### 15.1. Dependency graph không đồng nghĩa runtime reachability

Maven SBOM liệt kê dependency được resolve trong build. Nó không khẳng định mọi class/method đều được nạp hoặc gọi trong production. Đừng loại component chỉ vì “không thấy được dùng” nếu chưa có bằng chứng và policy phù hợp.

### 15.2. Dependency tải động

Một số ứng dụng tải plugin, script, extension hoặc binary lúc runtime. Những thành phần này có thể không nằm trong Maven dependency graph hoặc image lúc build. Cần inventory riêng từ artifact repository, runtime configuration hoặc image/host scan.

### 15.3. Maven scope và profile

Nếu CI build với profile khác local, dependency graph có thể thay đổi. Tạo SBOM từ cùng profile và dependency locks với release. Kiểm tra provided, system, test dependencies, optional dependencies và module exclusions.

### 15.4. SBOM của image cần scan đúng image

Nếu SBOM được tạo từ tag trước khi image push, sau đó tag bị ghi đè, file có thể mô tả image cũ. Hãy scan image sau khi build/push và gắn kết quả với digest đã resolve.

### 15.5. SBOM không thay vulnerability scanner

CycloneDX mô tả package inventory và metadata. Để tìm CVE cần scanner cùng vulnerability database. Để xác định exploitability cần context, VEX và phân tích ứng dụng. Để chứng minh nguồn gốc build cần provenance/attestation.

### 15.6. SBOM có thể chứa thông tin nhạy cảm về hệ thống

Tên thư viện nội bộ, version, module, URL repository và dependency relationships có thể là dữ liệu nhạy cảm. Hãy kiểm tra external references và custom properties trước khi công bố ra ngoài tổ chức. Không thêm tokens, credentials hoặc secrets vào SBOM.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Không có target/classes/META-INF/sbom | CycloneDX plugin chưa được kích hoạt hoặc goal chưa chạy | Kiểm tra parent POM, plugin declaration, effective POM |
| Có target/bom.json nhưng JAR không có SBOM | Output không nằm trong resource output trước package | Đặt output vào project.build.outputDirectory/META-INF/sbom hoặc dùng Boot parent config |
| /actuator/sbom trả 404 | Chưa thêm actuator, chưa expose endpoint hoặc SBOM không được nhúng | Kiểm tra dependency, properties, JAR entry |
| /actuator/sbom/application trả lỗi | Resource path hoặc format metadata không đúng | Kiểm tra file trong JAR và media type |
| Maven chỉ sinh BOM cho một module | Dùng makeBom thay vì aggregate | Dùng makeAggregateBom cho reactor nếu cần |
| Aggregate thiếu module | Module không thuộc reactor/profile hiện tại hoặc bị exclude | Xem Maven reactor, profiles và exclusion config |
| SBOM có test libraries | Include test scope bật hoặc config bị override | Đặt includeTestScope=false cho runtime BOM |
| SBOM có package không nằm trong JAR | provided/system scope hoặc scope policy quá rộng | Xem scope và đối chiếu packaged artifact |
| Component thiếu license | Repository metadata không cung cấp license | Kiểm tra nguồn package, bổ sung review; không tự đoán license |
| Plugin báo schema không hỗ trợ | Version plugin cũ hơn schema yêu cầu | Chọn plugin/schema tương thích |
| Validator báo sai specVersion | Truyền input-version không khớp file | Đọc specVersion và chọn đúng phiên bản |
| SBOM image thiếu JRE/OS package | Đang dùng project SBOM thay image SBOM | Scan final OCI image bằng Syft/Docker Scout |
| Paketo SBOM không có build tools | Chỉ tải launch-time SBOM | Thu thập build-time SBOM khi chạy pack build |
| Grype không có kết quả | SBOM rỗng/format sai hoặc database stale | Validate file, kiểm tra DB/network và scanner logs |
| SBOM khác giữa local và CI | Profiles, dependency resolution, plugin versions hoặc source khác | So commit, effective POM, dependency tree và toolchain |
| Maven config không nhận outputName | Plugin execution từ Spring Boot parent bị merge | Xem effective POM; dùng execution ID riêng cho custom goal |
| SBOM không khớp image digest | Image đã đổi sau khi tạo SBOM | Scan lại đúng digest được phát hành |
| SBOM public làm lộ dependency nội bộ | Endpoint/file không được kiểm soát | Hạn chế Actuator, registry và artifact permissions |
| Build thành công nhưng không upload SBOM | Pipeline thiếu bước publish artifact | Thêm upload/retention gate và kiểm tra exit status |

**Thứ tự điều tra:** goal/plugin có chạy không → file có được sinh không → nội dung/schema đúng không → JAR có nhúng không → image có được scan không → SBOM có gắn đúng digest không → scanner/policy có đọc được không.

## 17. Bài tập tự kiểm tra

**1. SBOM là gì?**

Đáp án: Bản kê có cấu trúc về các thành phần phần mềm và quan hệ của chúng trong một sản phẩm/artifact. Nó phục vụ truy vết, vulnerability management và license review.

**2. CycloneDX Maven Plugin tạo SBOM từ đâu?**

Đáp án: Từ Maven project/dependency model và các dependencies đã resolve. Nó không tự scan mọi package hệ điều hành trong container.

**3. Khác nhau giữa makeBom và makeAggregateBom?**

Đáp án: makeBom tạo BOM cho module hiện tại; makeAggregateBom tạo aggregate BOM tại root cho Maven reactor và có thể tạo BOM theo module.

**4. Vì sao Spring Boot đóng SBOM trong META-INF/sbom?**

Đáp án: Để resource đi cùng executable archive, giúp Actuator và các công cụ đọc metadata tìm được SBOM gắn với application artifact.

**5. /actuator/sbom và /actuator/sbom/application khác nhau thế nào?**

Đáp án: Endpoint đầu liệt kê các SBOM ID; endpoint thứ hai trả nội dung SBOM cụ thể.

**6. Vì sao cần bảo vệ SBOM endpoint?**

Đáp án: Nó có thể tiết lộ tên/version dependency và cấu trúc thành phần nội bộ. Nên giới hạn truy cập cho security/operations.

**7. Vì sao cần image SBOM nếu đã có Maven SBOM?**

Đáp án: Maven SBOM tập trung dependency graph của ứng dụng; image SBOM có thể phát hiện thêm JRE, OS packages và thành phần được đóng vào final image.

**8. pack sbom download của Paketo có bao gồm build-time dependencies không?**

Đáp án: SBOM tải theo cách này tập trung launch-time dependencies. Build-time SBOM cần thu thập trong quá trình build với tùy chọn output phù hợp.

**9. SBOM có phải vulnerability report không?**

Đáp án: Không. SBOM là inventory; scanner như Grype đối chiếu package với vulnerability database để tạo findings.

**10. Vì sao phải gắn SBOM với image digest?**

Đáp án: Tag có thể thay đổi. Digest xác định nội dung image cụ thể mà SBOM và scan report mô tả.

**11. Nếu plugin không tìm thấy license của một component thì có thể tự điền MIT không?**

Đáp án: Không. Phải kiểm tra metadata/nguồn license và ghi nhận trạng thái chưa xác định nếu chưa có bằng chứng.

**12. Có thể tạo một SBOM duy nhất cho application, build tools, base image và runtime host không?**

Đáp án: Có thể tổng hợp inventory ở mức hệ thống bằng công cụ/phương pháp phù hợp, nhưng phải giữ nguồn gốc và phạm vi của từng bản kê rõ ràng. Một BOM tổng hợp không nên làm mất thông tin thành phần đến từ app, OS, builder hay host.

## 18. Checklist áp dụng vào dự án thật

- [ ] Xác định SBOM mô tả source project, executable JAR hay container image.
- [ ] Chọn CycloneDX/SPDX schema mà registry, scanner và consumer hỗ trợ.
- [ ] Pin version plugin và schema; không dùng snapshot tùy tiện.
- [ ] Maven: chọn makeBom hoặc makeAggregateBom đúng phạm vi.
- [ ] Gradle: cấu hình CycloneDX plugin và kiểm tra task cyclonedxBom.
- [ ] Đồng bộ profiles, scopes, dependency locks và reactor với release.
- [ ] Kiểm tra metadata component, versions, PURLs, dependency graph, license và hashes.
- [ ] Validate SBOM theo đúng schema.
- [ ] Kiểm tra SBOM đã được đóng vào JAR nếu cần Actuator integration.
- [ ] Hạn chế truy cập /actuator/sbom bằng security/network policy.
- [ ] Tạo image SBOM cho final image, bao gồm OS/JRE packages khi công cụ hỗ trợ.
- [ ] Thu thập build-time SBOM nếu policy yêu cầu.
- [ ] Scan SBOM/image bằng vulnerability database cập nhật.
- [ ] Review license và CVE exceptions bằng quy trình được phê duyệt.
- [ ] Gắn SBOM/scan report với commit, JAR checksum và image digest.
- [ ] Ký/attest artifact và SBOM nếu release policy yêu cầu.
- [ ] Lưu SBOM cùng release artifacts, có retention và access control.
- [ ] Có owner cập nhật plugin, scanner, builder và base image.

**Kết luận:** CycloneDX Maven/Gradle Plugin là cách phù hợp để tạo **application dependency SBOM** từ build model. Spring Boot có thể đóng SBOM vào executable JAR và expose qua Actuator. Syft, Docker Scout và Buildpacks SBOM bổ sung inventory ở **container image level**. Muốn dùng SBOM có giá trị trong vận hành, hãy validate schema, xác minh phạm vi, scan vulnerabilities, bảo vệ thông tin và liên kết từng SBOM với đúng source/artifact/image digest.

## 19. Tài liệu tham khảo chính thức

1. [Spring Boot 4.1 — Generate a CycloneDX SBOM](https://docs.spring.io/spring-boot/how-to/build.html)
2. [Spring Boot 4.1 — Actuator SBOM Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
3. [CycloneDX Maven Plugin — Usage and Defaults](https://cyclonedx.github.io/cyclonedx-maven-plugin/)
4. [CycloneDX Maven Plugin — makeBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeBom-mojo.html)
5. [CycloneDX Maven Plugin — makeAggregateBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeAggregateBom-mojo.html)
6. [CycloneDX Maven Plugin — Releases](https://github.com/CycloneDX/cyclonedx-maven-plugin/releases)
7. [CycloneDX Specification Overview](https://cyclonedx.org/specification/overview/)
8. [CycloneDX CLI — Validate, Diff, Merge and Sign](https://github.com/CycloneDX/cyclonedx-cli)
9. [Paketo — How to Access an SBOM](https://paketo.io/docs/howto/sbom/)
10. [Paketo — SBOM Concepts and Formats](https://paketo.io/docs/concepts/sbom/)
11. [Anchore Syft — Generate SBOMs from Images and Filesystems](https://github.com/anchore/syft)
12. [Anchore Grype — Scan an SBOM](https://oss.anchore.com/docs/guides/vulnerability/scan-targets/)
13. [Docker Scout — Generate or Display an Image SBOM](https://docs.docker.com/reference/cli/docker/scout/sbom/)
14. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
