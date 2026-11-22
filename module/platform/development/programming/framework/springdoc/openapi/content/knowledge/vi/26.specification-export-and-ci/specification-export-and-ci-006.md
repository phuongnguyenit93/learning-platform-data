# Cấu hình địa chỉ tài liệu, thư mục và tên tệp đầu ra

springdoc-openapi tạo đặc tả OpenAPI khi ứng dụng Spring Boot đang chạy và cung cấp tài liệu qua HTTP. Khi cần lưu đặc tả thành tệp trong quá trình build, có thể dùng springdoc-openapi Maven Plugin hoặc Gradle Plugin. Hai plugin gọi endpoint tài liệu của ứng dụng, tải nội dung JSON/YAML rồi ghi vào thư mục và tên tệp được cấu hình.

Ba giá trị cần phân biệt:

1. **Địa chỉ tài liệu (apiDocsUrl):** URL HTTP mà plugin gọi để lấy OpenAPI.
2. **Thư mục đầu ra (outputDir):** thư mục trên máy build dùng để lưu tệp đã tải.
3. **Tên tệp đầu ra (outputFileName):** tên tệp được tạo bên trong thư mục đó.

Ví dụ, plugin gọi `http://localhost:8080/v3/api-docs` rồi ghi nội dung vào `target/openapi/openapi.json`. Nếu ứng dụng đổi endpoint tài liệu sang `/docs/spec`, URL tải tài liệu phải đổi. Nếu muốn lưu sang `build/contracts`, thay outputDir. Nếu muốn đặt tên `shop-api-v1.json`, thay outputFileName.

Các thuộc tính này thuộc plugin build. Chúng không thay đổi endpoint runtime của springdoc và cũng không thay đổi URL Swagger UI.

## 1. Phân biệt endpoint runtime và tệp export

Springdoc mặc định cung cấp OpenAPI JSON tại `/v3/api-docs` và YAML tại `/v3/api-docs.yaml`. Có thể thay endpoint JSON bằng `springdoc.api-docs.path`:

~~~yaml
springdoc:
  api-docs:
    path: /docs/spec
~~~

Khi đó, ứng dụng phục vụ JSON tại `/docs/spec`. Nếu build plugin vẫn gọi URL mặc định `/v3/api-docs`, plugin sẽ gọi sai endpoint.

Đường dẫn Swagger UI là cấu hình riêng. `springdoc.swagger-ui.path` chỉ thay URL trang giao diện; nó không thay endpoint OpenAPI mà plugin cần gọi.

| Thành phần | Ví dụ | Điều khiển bởi |
| --- | --- | --- |
| OpenAPI JSON runtime | `/v3/api-docs` | `springdoc.api-docs.path` |
| OpenAPI YAML runtime | `/v3/api-docs.yaml` | Endpoint YAML của springdoc |
| Swagger UI page | `/swagger-ui.html` | `springdoc.swagger-ui.path` |
| URL plugin tải tài liệu | `http://localhost:8080/v3/api-docs` | `apiDocsUrl` |
| Thư mục tệp được ghi | `target/openapi` | `outputDir` |
| Tên tệp được ghi | `shop-api.json` | `outputFileName` |

Hãy xác định URL runtime trước, sau đó cấu hình plugin trỏ đúng URL đó. Cuối cùng mới chọn nơi lưu và tên tệp trên máy build.

## 2. Luồng export trong quá trình build

Plugin không phân tích source code Java để tự dựng lại schema. Nó khởi động ứng dụng Spring Boot, gọi HTTP endpoint do springdoc cung cấp và lưu response thành tệp.

~~~mermaid
flowchart TD
    A[Build bắt đầu] --> B[Khởi động Spring Boot]
    B --> C[Springdoc tạo OpenAPI runtime]
    C --> D[Plugin gọi apiDocsUrl]
    D --> E{HTTP response thành công?}
    E -->|Có| F[Tải JSON hoặc YAML]
    F --> G[Ghi outputDir/outputFileName]
    G --> H[Đưa tệp vào artifact hoặc CI]
    E -->|Không| I[Báo lỗi hoặc tiếp tục tùy failOnError]
    H --> J[Dừng ứng dụng]
~~~

Do tài liệu được lấy từ ứng dụng đang chạy, profile, biến môi trường, database, security và các bean có thể ảnh hưởng đến OpenAPI được sinh ra. Plugin cần khởi động được ứng dụng trong môi trường build và endpoint phải truy cập được từ tiến trình build.

## 3. Chọn đúng apiDocsUrl

URL mặc định thường là:

~~~text
http://localhost:8080/v3/api-docs
~~~

Nếu ứng dụng thay đổi cổng hoặc context path, URL phải phản ánh địa chỉ mới:

| Cấu hình ứng dụng | apiDocsUrl tương ứng |
| --- | --- |
| Cổng 8080, không có context path | `http://localhost:8080/v3/api-docs` |
| Cổng 9090 | `http://localhost:9090/v3/api-docs` |
| Context path `/shop` | `http://localhost:8080/shop/v3/api-docs` |
| Custom API docs path `/docs/spec` | `http://localhost:8080/docs/spec` |
| Management port 9090, base path `/actuator` | Ví dụ `http://localhost:9090/actuator/openapi` nếu đây là endpoint springdoc được expose |

Không đoán URL từ tên ứng dụng hoặc URL Swagger UI. Mở endpoint trực tiếp hoặc kiểm tra cấu hình springdoc và Actuator để xác nhận URL chính xác.

Nếu API docs yêu cầu xác thực, plugin cần gửi header phù hợp. Nếu dùng reverse proxy, gateway hoặc HTTPS, URL phải truy cập được từ môi trường build và certificate phải được JVM tin cậy.

## 4. Cấu hình URL, thư mục và tên tệp với Maven

Springdoc OpenAPI Maven Plugin có goal `generate`, mặc định chạy ở phase `integration-test`. Plugin làm việc cùng `spring-boot-maven-plugin`: ứng dụng được khởi động trước integration test, plugin tải tài liệu rồi ứng dụng được dừng ở phase `post-integration-test`.

Các giá trị mặc định:

| Thuộc tính Maven | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `apiDocsUrl` | `http://localhost:8080/v3/api-docs` | URL lấy JSON hoặc YAML |
| `outputDir` | `target` (project.build.directory) | Thư mục ghi tệp |
| `outputFileName` | `openapi.json` | Tên tệp đầu ra |
| `attachArtifact` | `false` | Có gắn tệp vào artifact Maven để install/deploy hay không |
| `attachArtifactClassifier` | `openapi` | Classifier khi attach |
| `timeout` | `60` giây | Timeout kết nối và đọc |
| `failOnError` | `false` | Build có thất bại khi tải/ghi tài liệu lỗi hay không |

Ví dụ cấu hình trong `pom.xml`:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
      <configuration>
        <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
      </configuration>
      <executions>
        <execution>
          <id>pre-integration-test</id>
          <goals><goal>start</goal></goals>
        </execution>
        <execution>
          <id>post-integration-test</id>
          <goals><goal>stop</goal></goals>
        </execution>
      </executions>
    </plugin>

    <plugin>
      <groupId>org.springdoc</groupId>
      <artifactId>springdoc-openapi-maven-plugin</artifactId>
      <version>1.6</version>
      <executions>
        <execution>
          <id>generate-openapi</id>
          <phase>integration-test</phase>
          <goals><goal>generate</goal></goals>
        </execution>
      </executions>
      <configuration>
        <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <outputFileName>shop-api.json</outputFileName>
        <failOnError>true</failOnError>
        <timeout>60</timeout>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Chạy:

~~~bash
mvn verify
~~~

Tệp được ghi tại `target/openapi/shop-api.json`. Trong cấu hình này, apiDocsUrl trỏ đến endpoint JSON, outputDir chọn thư mục `target/openapi`, outputFileName đặt tên `shop-api.json` và failOnError khiến build báo lỗi nếu không tải hoặc không ghi được tài liệu.

`outputDir` là thư mục, không phải đường dẫn đầy đủ của tệp. `outputFileName` là tên tệp đặt bên trong thư mục đó. Tách hai giá trị giúp đổi thư mục mà không phải đổi tên tệp.

## 5. Xuất YAML bằng Maven

Để xuất YAML, gọi endpoint YAML và đặt phần mở rộng tệp tương ứng:

~~~xml
<configuration>
  <apiDocsUrl>http://localhost:8080/v3/api-docs.yaml</apiDocsUrl>
  <outputDir>${project.build.directory}/openapi</outputDir>
  <outputFileName>shop-api.yaml</outputFileName>
  <failOnError>true</failOnError>
</configuration>
~~~

Kết quả: `target/openapi/shop-api.yaml`.

Không chỉ đổi tên tệp JSON thành `.yaml`. Phần mở rộng không chuyển đổi nội dung. Endpoint `/v3/api-docs.yaml` mới là nơi yêu cầu springdoc trả YAML; tên tệp chỉ giúp người dùng và công cụ nhận biết định dạng đã tải.

## 6. Dùng biến Maven để thay đổi thư mục và tên tệp

Có thể dùng Maven property để tái sử dụng và ghi đè theo build:

~~~xml
<properties>
  <openapi.output.dir>${project.build.directory}/contracts</openapi.output.dir>
  <openapi.output.file>shop-api.json</openapi.output.file>
  <openapi.url>http://localhost:8080/v3/api-docs</openapi.url>
</properties>

<plugin>
  <groupId>org.springdoc</groupId>
  <artifactId>springdoc-openapi-maven-plugin</artifactId>
  <version>1.6</version>
  <configuration>
    <apiDocsUrl>${openapi.url}</apiDocsUrl>
    <outputDir>${openapi.output.dir}</outputDir>
    <outputFileName>${openapi.output.file}</outputFileName>
    <failOnError>true</failOnError>
  </configuration>
</plugin>
~~~

Ghi đè từ command line:

~~~bash
mvn verify \
  -Dopenapi.output.dir=target/contracts/public \
  -Dopenapi.output.file=public-api.json
~~~

Các user property của plugin cũng có thể truyền trực tiếp:

~~~bash
mvn verify \
  -Dspringdoc.outputDir=target/contracts \
  -Dspringdoc.outputFileName=shop-api.json \
  -Dspringdoc.apiDocsUrl=http://localhost:8080/v3/api-docs
~~~

## 7. Đưa OpenAPI file vào Maven artifact

Mặc định `attachArtifact` là false. Khi đặt true, plugin gắn tệp OpenAPI vào project artifact để có thể install hoặc deploy cùng các artifact khác:

~~~xml
<configuration>
  <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
  <outputDir>${project.build.directory}/openapi</outputDir>
  <outputFileName>shop-api.json</outputFileName>
  <attachArtifact>true</attachArtifact>
  <attachArtifactClassifier>openapi</attachArtifactClassifier>
  <failOnError>true</failOnError>
</configuration>
~~~

Classifier mặc định là `openapi`. Nếu cùng build nhiều tài liệu, mỗi execution cần classifier riêng khi attach để tránh trùng artifact coordinates.

Việc attach không thay đổi nơi ghi tệp cục bộ. outputDir và outputFileName vẫn quyết định vị trí tệp trong workspace; attachArtifact quyết định tệp có được gắn vào Maven project để publish cùng artifact hay không.

## 8. Xuất nhiều group bằng Maven

Nếu ứng dụng khai báo các group như public, admin hoặc partner, mỗi group có endpoint OpenAPI riêng. Có thể tạo nhiều execution, mỗi execution dùng URL và tên tệp riêng:

~~~xml
<plugin>
  <groupId>org.springdoc</groupId>
  <artifactId>springdoc-openapi-maven-plugin</artifactId>
  <version>1.6</version>
  <executions>
    <execution>
      <id>export-public-api</id>
      <goals><goal>generate</goal></goals>
      <configuration>
        <apiDocsUrl>http://localhost:8080/v3/api-docs/public</apiDocsUrl>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <outputFileName>public-api.json</outputFileName>
        <attachArtifactClassifier>public-openapi</attachArtifactClassifier>
        <attachArtifact>true</attachArtifact>
        <failOnError>true</failOnError>
      </configuration>
    </execution>
    <execution>
      <id>export-admin-api</id>
      <goals><goal>generate</goal></goals>
      <configuration>
        <apiDocsUrl>http://localhost:8080/v3/api-docs/admin</apiDocsUrl>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <outputFileName>admin-api.json</outputFileName>
        <attachArtifactClassifier>admin-openapi</attachArtifactClassifier>
        <attachArtifact>true</attachArtifact>
        <failOnError>true</failOnError>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

Kết quả gồm `target/openapi/public-api.json` và `target/openapi/admin-api.json`. Tên group trong URL phải khớp với group được khai báo trong ứng dụng.

## 9. Cấu hình URL, thư mục và tên tệp với Gradle

Springdoc OpenAPI Gradle Plugin cung cấp task `generateOpenApiDocs`. Plugin khởi động ứng dụng bằng cấu hình của task `bootRun`, tải OpenAPI description rồi dừng ứng dụng. Mặc định, tệp được ghi tại `build/openapi.json`.

Ví dụ Kotlin DSL trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("org.springdoc.openapi-gradle-plugin") version "2.1.0"
}

dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-api:2.10.0")
}

openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("shop-api.json")
    waitTimeInSeconds.set(60)
}
~~~

Chạy:

~~~bash
./gradlew generateOpenApiDocs
~~~

Kết quả: `build/openapi/shop-api.json`.

Trong Gradle, apiDocsUrl là URL HTTP được tải; outputDir là thư mục đầu ra; outputFileName là tên tệp; waitTimeInSeconds là thời gian chờ ứng dụng khởi động và sẵn sàng phục vụ endpoint. Gradle Plugin cần ứng dụng có dependency springdoc để cung cấp endpoint.

## 10. Cấu hình tương đương bằng Groovy DSL

Nếu dự án dùng `build.gradle` thay vì `build.gradle.kts`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'org.springdoc.openapi-gradle-plugin' version '2.1.0'
}

dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-api:2.10.0'
}

openApi {
    apiDocsUrl = 'http://localhost:8080/v3/api-docs'
    outputDir = layout.buildDirectory.dir('openapi')
    outputFileName = 'shop-api.json'
    waitTimeInSeconds = 60
}
~~~

Hai DSL có cùng mục tiêu. Chọn đúng cú pháp theo loại build script; không trộn `set(...)` của Kotlin DSL vào Groovy DSL.

## 11. Xuất YAML bằng Gradle

Với Gradle Plugin, URL kết thúc bằng `.yaml` khiến plugin lưu nội dung dưới định dạng YAML:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs.yaml")
    outputDir.set(layout.buildDirectory.dir("contracts"))
    outputFileName.set("shop-api.yaml")
}
~~~

Kết quả: `build/contracts/shop-api.yaml`. Nếu dùng URL JSON nhưng đặt tên tệp `.yaml`, nội dung vẫn là JSON. Hãy đồng bộ endpoint, nội dung và phần mở rộng tên tệp.

## 12. Dùng customBootRun để chọn profile sinh tài liệu

Tài liệu được tạo từ ứng dụng đang chạy, vì vậy profile ảnh hưởng đến cấu hình và có thể ảnh hưởng đến OpenAPI. Ví dụ profile `openapi` có thể tắt kết nối dịch vụ ngoài, nạp dữ liệu kiểm thử và bật tài liệu cho build.

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("contracts"))
    outputFileName.set("shop-api.json")
    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

`customBootRun` cho phép tùy chỉnh arguments, JVM arguments, system properties, environment variables, main class, classpath và working directory. Những thuộc tính được chỉ định thay thế giá trị tương ứng từ `bootRun`; các thuộc tính còn lại tiếp tục dùng cấu hình của `bootRun`.

Nếu ứng dụng chạy ở port 9090 trong cấu hình riêng, hãy đồng bộ cả customBootRun và apiDocsUrl:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs")
    customBootRun {
        args.set(listOf("--server.port=9090", "--spring.profiles.active=openapi"))
    }
}
~~~

## 13. Xuất nhiều group bằng Gradle

Gradle Plugin hỗ trợ `groupedApiMappings`, là map giữa URL tài liệu của từng group và tên tệp đầu ra:

~~~kotlin
openApi {
    outputDir.set(layout.buildDirectory.dir("contracts"))
    groupedApiMappings.set(
        mapOf(
            "http://localhost:8080/v3/api-docs/public" to "public-api.json",
            "http://localhost:8080/v3/api-docs/admin" to "admin-api.json",
            "http://localhost:8080/v3/api-docs/partner" to "partner-api.json"
        )
    )
}
~~~

Khi dùng groupedApiMappings, plugin bỏ qua apiDocsUrl và outputFileName đơn lẻ. Mỗi URL trong map được tải và ghi thành tệp riêng trong outputDir.

## 14. URL có xác thực, HTTPS hoặc reverse proxy

Một số ứng dụng bảo vệ OpenAPI endpoint bằng Spring Security hoặc chỉ truy cập được qua HTTPS. Cả Maven và Gradle plugin đều có cách gửi HTTP header để tải tài liệu.

Maven:

~~~xml
<configuration>
  <apiDocsUrl>https://localhost:8443/v3/api-docs</apiDocsUrl>
  <outputDir>${project.build.directory}/openapi</outputDir>
  <outputFileName>internal-api.json</outputFileName>
  <headers>
    <Authorization>Bearer ${env.OPENAPI_TOKEN}</Authorization>
  </headers>
  <failOnError>true</failOnError>
</configuration>
~~~

Gradle Kotlin DSL:

~~~kotlin
val openApiToken = providers.environmentVariable("OPENAPI_TOKEN")

openApi {
    apiDocsUrl.set("https://localhost:8443/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("internal-api.json")
    requestHeaders.set(
        openApiToken.orNull?.let {
            mapOf("Authorization" to "Bearer $it")
        } ?: emptyMap()
    )
}
~~~

Giá trị token nên được cấp từ secret của CI, không commit vào pom.xml hoặc build.gradle. Nếu dùng HTTPS với certificate nội bộ mà JVM chưa tin cậy, Gradle Plugin hỗ trợ trust store và trust store password. Tạo trust store chứa CA/certificate cần tin cậy; không tắt xác minh TLS để né lỗi certificate.

Nếu ứng dụng nằm sau reverse proxy, URL cần truy cập được từ máy build. Khi ứng dụng sinh server URL dựa trên forwarded headers, có thể gửi x-forwarded-host hoặc x-forwarded-port trong request headers theo cấu hình của ứng dụng. Điều này tác động đến URL server được sinh trong OpenAPI; nó không thay đổi thư mục hay tên tệp đầu ra.

## 15. Xuất tài liệu từ management port hoặc custom path

Nếu springdoc được đặt trên management port riêng, plugin cần gọi URL management endpoint thay vì URL mặc định trên application port.

~~~yaml
server:
  port: 8080
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: "health,openapi,swagger-ui"
springdoc:
  use-management-port: true
~~~

Với cấu hình trên, xác nhận endpoint OpenAPI do springdoc đăng ký dưới Actuator base path, ví dụ `/actuator/openapi`, rồi cấu hình:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/actuator/openapi")
    outputDir.set(layout.buildDirectory.dir("contracts"))
    outputFileName.set("shop-api.json")
}
~~~

Nếu đổi management.endpoints.web.base-path, đổi URL plugin tương ứng. Tương tự, nếu springdoc.api-docs.path thay đổi endpoint runtime trên application port, plugin phải dùng URL mới. outputDir và outputFileName không phụ thuộc vào những path runtime đó.

## 16. Export thủ công bằng curl

Không nhất thiết phải cấu hình build plugin cho một lần tải tài liệu. Có thể gọi trực tiếp endpoint bằng curl:

~~~bash
mkdir -p build/contracts
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output build/contracts/shop-api.json
~~~

Xuất YAML:

~~~bash
mkdir -p build/contracts
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output build/contracts/shop-api.yaml
~~~

Với endpoint cần token:

~~~bash
curl --fail --silent --show-error \
  -H "Authorization: Bearer $OPENAPI_TOKEN" \
  http://localhost:8080/v3/api-docs \
  --output build/contracts/internal-api.json
~~~

Tham số `--output` quyết định nơi lưu và tên tệp trong lần gọi curl. Thư mục phải tồn tại trước khi ghi. Dùng `--fail` để lệnh trả mã lỗi với HTTP status 4xx/5xx, giúp pipeline không âm thầm lưu trang lỗi thành file OpenAPI.

## 17. Kiểm tra tệp sau khi export

Sau khi build, kiểm tra cả vị trí, tên, định dạng và nội dung:

~~~bash
ls -l target/openapi
head -n 20 target/openapi/shop-api.json
jq -r '.openapi, .info.title, .info.version' target/openapi/shop-api.json
~~~

Với Gradle:

~~~bash
ls -l build/contracts
jq -r '.openapi, .info.title, .info.version' build/contracts/shop-api.json
~~~

Với YAML, dùng công cụ đọc YAML phù hợp để xác nhận nội dung. Không chỉ dựa vào phần mở rộng tên tệp. Hãy kiểm tra nội dung thực sự có trường openapi, info, paths và components như mong đợi.

Định dạng đầu ra còn có khác biệt nhỏ giữa hai plugin: Maven ghi nội dung đúng như endpoint trả về; nếu muốn JSON pretty-print, có thể bật thuộc tính springdoc.writer-with-default-pretty-printer=true trong ứng dụng. Gradle Plugin pretty-print JSON trước khi ghi, còn YAML được ghi theo nội dung endpoint trả về.

Có thể kiểm tra file không rỗng:

~~~bash
test -s build/contracts/shop-api.json
~~~

Nếu tệp không tồn tại, kiểm tra apiDocsUrl, trạng thái ứng dụng, thời gian chờ startup, quyền truy cập và outputDir. Nếu tệp tồn tại nhưng chứa trang lỗi, kiểm tra HTTP status, redirect, authentication và response content type.

## 18. Đưa tệp export vào CI artifact

Thư mục target hoặc build thường được xem là thư mục build và có thể bị xóa khi clean. Trong CI, sau khi tạo tài liệu, cấu hình bước upload artifact trỏ đến đúng đường dẫn:

~~~text
Maven:
target/openapi/shop-api.json

Gradle:
build/contracts/shop-api.json
~~~

Nếu muốn lưu tệp trong repository, hãy chọn một thư mục được quản lý rõ ràng, ví dụ `docs/api/`, và cân nhắc commit snapshot chỉ khi dự án muốn review thay đổi hợp đồng qua Git. Nếu mục tiêu là artifact CI, giữ trong thư mục build và upload như một build artifact.

Với Maven, có thể dùng `attachArtifact=true` để install/deploy tài liệu cùng artifact Maven. Với Gradle, có thể thêm task copy hoặc publish riêng tùy pipeline. Việc ghi tệp ra outputDir tự nó không có nghĩa tệp đã được publish lên repository hoặc artifact store.

## 19. Những lỗi thường gặp

**Plugin không kết nối được localhost.** Ứng dụng chưa khởi động, đang chạy cổng khác, context path khác hoặc endpoint path đã đổi. Xác nhận URL trực tiếp trước khi sửa outputDir.

**Đổi springdoc.swagger-ui.path nhưng plugin vẫn lỗi.** Thuộc tính đó thay trang giao diện. Plugin cần URL OpenAPI, thường là /v3/api-docs hoặc custom springdoc.api-docs.path.

**Đổi outputFileName nhưng không tìm thấy tệp.** Kiểm tra outputDir và outputFileName cùng nhau. Tệp nằm trong thư mục outputDir với đúng tên đã cấu hình.

**Tệp có đuôi YAML nhưng nội dung là JSON.** URL vẫn gọi endpoint JSON. Hãy gọi /v3/api-docs.yaml và dùng tên tệp .yaml.

**Build thành công nhưng không có tệp.** Maven plugin mặc định failOnError=false, nên lỗi tải tài liệu có thể chỉ được log. Bật failOnError=true trong CI.

**Maven build lỗi nhưng ứng dụng vẫn chạy.** Nếu build thất bại trước phase post-integration-test, goal stop có thể không được gọi. Kiểm tra và dừng tiến trình cũ trước lần build tiếp theo.

**Gradle báo không kết nối được sau thời gian chờ.** Kiểm tra log startup, URL và tăng waitTimeInSeconds khi ứng dụng cần nhiều thời gian khởi động.

**Gradle báo port đã được sử dụng.** Có tiến trình khác đang nghe trên port của apiDocsUrl, có thể là ứng dụng còn sót từ build trước. Dừng tiến trình đó hoặc chọn port khác đồng bộ với cấu hình.

**Endpoint trả 401 hoặc 403.** Cấp header xác thực cho plugin qua headers/requestHeaders và lấy token từ secret của CI.

**Plugin HTTP client không tải được endpoint nhưng trình duyệt vẫn mở được.** Kiểm tra DNS, route mạng, proxy, certificate và header xác thực từ môi trường build. CORS là chính sách của trình duyệt; plugin gọi endpoint từ tiến trình build nên lỗi tải của plugin thường cần chẩn đoán ở kết nối HTTP, xác thực hoặc TLS.

**HTTPS báo certificate không tin cậy.** Cấu hình trust store với CA/certificate phù hợp. Không bỏ qua kiểm tra TLS.

**Tài liệu sinh ra có server URL sai host hoặc port.** Kiểm tra forwarded headers và cấu hình reverse proxy. requestHeaders có thể gửi các header forwarded nếu ứng dụng được cấu hình để tin và xử lý chúng.

**Nhiều group ghi đè cùng một tệp.** Dùng outputFileName riêng cho từng group và classifier riêng nếu attach vào Maven repository.

**Gradle groupedApiMappings không dùng apiDocsUrl.** Khi cấu hình groupedApiMappings, plugin bỏ qua apiDocsUrl và outputFileName đơn lẻ. Đưa URL và filename của từng group vào map.

## 20. Checklist cấu hình đầu ra

- [ ] Xác định endpoint OpenAPI runtime đang phục vụ JSON hoặc YAML.
- [ ] Kiểm tra cổng, context path, custom API docs path hoặc management port.
- [ ] Đặt apiDocsUrl trỏ đúng endpoint, không trỏ nhầm Swagger UI.
- [ ] Đặt outputDir là thư mục đích.
- [ ] Đặt outputFileName là tên tệp có phần mở rộng đúng định dạng.
- [ ] Với YAML, gọi endpoint .yaml và đặt tên .yaml.
- [ ] Với Maven CI, bật failOnError=true.
- [ ] Với Gradle, đặt waitTimeInSeconds phù hợp startup time.
- [ ] Nếu endpoint cần xác thực, cấp headers/requestHeaders từ secret của CI.
- [ ] Với HTTPS nội bộ, cấu hình trust store đúng.
- [ ] Nếu xuất nhiều group, dùng tên tệp riêng và kiểm tra từng URL.
- [ ] Kiểm tra tệp tồn tại, không rỗng và parse được sau build.
- [ ] Cấu hình CI upload đúng đường dẫn output.
- [ ] Phân biệt lưu tệp cục bộ với attach/publish artifact.

## 21. Kết luận

Để export OpenAPI ổn định, trước tiên xác định URL runtime mà springdoc đang phục vụ. Sau đó cấu hình plugin gọi đúng apiDocsUrl, ghi vào outputDir và đặt tên bằng outputFileName. Maven mặc định ghi target/openapi.json; Gradle mặc định ghi build/openapi.json. Định dạng JSON/YAML phụ thuộc endpoint được gọi, vì vậy cần đồng bộ URL với phần mở rộng tên tệp. Trong CI, hãy bật fail-on-error, xử lý xác thực và HTTPS đúng cách, rồi kiểm tra và upload chính xác tệp được tạo.

## 22. Nguồn tham khảo

- [springdoc-openapi Maven and Gradle Plugins](https://springdoc.org/plugins.html): quy trình export, cấu hình Maven/Gradle, URL, thư mục, tên tệp và profile build.
- [springdoc-openapi Maven Plugin README](https://github.com/springdoc/springdoc-openapi-maven-plugin): apiDocsUrl, outputDir, outputFileName, attachArtifact, failOnError, headers và YAML.
- [springdoc-openapi Gradle Plugin README](https://github.com/springdoc/springdoc-openapi-gradle-plugin): openApi configuration, groupedApiMappings, customBootRun, requestHeaders, trustStore và YAML.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html): cấu hình runtime như springdoc.api-docs.path và springdoc.api-docs.enabled.
- [springdoc-openapi Getting Started](https://springdoc.org/getting-started.html): endpoint JSON/YAML mặc định và đường dẫn Swagger UI.
