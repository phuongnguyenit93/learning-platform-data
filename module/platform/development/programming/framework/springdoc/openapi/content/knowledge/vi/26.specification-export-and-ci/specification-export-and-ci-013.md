# Phân biệt hợp đồng được xuất lúc build với tài liệu của ứng dụng đang triển khai

Springdoc-openapi có thể cung cấp OpenAPI document trực tiếp từ ứng dụng đang chạy và cũng có thể xuất document thành file trong quá trình build. Hai cách này dùng cùng nguồn mô tả từ controller, model, annotation và cấu hình Spring, nhưng trả lời hai câu hỏi khác nhau: artifact được tạo từ một cấu hình build có kiểm soát là hợp đồng nào đã được kiểm tra và phát hành; endpoint trên môi trường triển khai đang công bố điều gì ở thời điểm hiện tại.

Điểm cần hiểu đúng là plugin export của Springdoc không phân tích source code độc lập ở pha compile. Plugin khởi chạy ứng dụng Spring Boot, gọi HTTP endpoint mà Springdoc cung cấp, tải JSON/YAML rồi ghi thành file. Vì document được tạo từ application context đang chạy, profile, property, bean, group, customizer, locale và request header của lần chạy đó đều có thể ảnh hưởng kết quả.

Bài học này xây dựng quy trình xuất OpenAPI lặp lại được trong Maven hoặc Gradle, quản lý artifact theo release, và đối chiếu artifact đó với tài liệu của ứng dụng đang triển khai để phát hiện configuration drift.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt OpenAPI endpoint runtime với file contract được tạo trong build.
- Giải thích vì sao “export lúc build” vẫn khởi chạy ứng dụng và gọi HTTP.
- Cấu hình `springdoc-openapi-maven-plugin` và `springdoc-openapi-gradle-plugin`.
- Chọn profile, port, headers, output path và group cho lần export.
- Xuất JSON hoặc YAML cho default document và từng `GroupedOpenApi`.
- Đóng gói OpenAPI file như một artifact có version.
- Kiểm tra tính tái lập và xác định nguyên nhân khiến hai lần export khác nhau.
- Đối chiếu artifact build với `/v3/api-docs` trên staging/production.
- Phân biệt thay đổi hợp đồng với khác biệt do môi trường triển khai.
- Đưa export, validation, semantic diff và runtime verification vào CI/CD.

## 1. Hai dạng tài liệu cần quản lý

Springdoc thường tạo OpenAPI document từ Spring application context. Có thể lấy document qua HTTP khi ứng dụng đang chạy hoặc tải nó trong một build task rồi lưu thành file.

### 1.1. Tài liệu runtime

Đây là document được phục vụ bởi ứng dụng đang hoạt động. Với cấu hình mặc định:

~~~text
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

Nếu có group, mỗi group có URL riêng:

~~~text
GET /v3/api-docs/public
GET /v3/api-docs/admin
~~~

Tài liệu runtime phản ánh application context và cấu hình mà instance đó đang dùng. Ví dụ, một instance staging chạy profile `staging`, một instance production chạy profile `prod`; nếu hai profile tạo bean hoặc `GroupedOpenApi` khác nhau, document có thể khác nhau.

### 1.2. Artifact được xuất trong build

Build plugin khởi động ứng dụng bằng cấu hình được chỉ định cho task, tải OpenAPI document qua HTTP rồi ghi ra thư mục build, ví dụ:

~~~text
target/openapi/openapi.json
build/openapi.json
~~~

File này có thể được:

- Lưu cùng build output để kiểm tra.
- Đưa vào semantic diff với bản phát hành trước.
- Đính kèm Maven artifact hoặc lưu trong artifact repository.
- Cấp cho SDK generator, API portal hoặc quy trình kiểm thử consumer.
- Phát hành như contract snapshot có liên kết tới commit và application version.

Artifact build là bằng chứng về document được sinh từ application instance trong build. Nó không tự chứng minh rằng mọi instance đã triển khai đang phục vụ cùng document đó.

## 2. “Build-time export” thực sự diễn ra như thế nào?

Springdoc FAQ gọi việc xuất JSON/YAML trong build là lấy tài liệu “compile time”. Về kỹ thuật, plugin export hoạt động bằng cách chạy ứng dụng rồi gọi endpoint OpenAPI:

~~~text
Compile / package application
          |
          v
Start Spring Boot application
with a controlled profile and properties
          |
          v
Wait for the application to become ready
          |
          v
GET /v3/api-docs (or a group URL)
          |
          v
Write JSON/YAML to the build directory
          |
          v
Validate and compare the contract
          |
          v
Stop the application
          |
          v
Publish the OpenAPI artifact
~~~

Vì vậy, plugin không chỉ đọc annotation lúc compile và tự dựng document trong một tiến trình độc lập. Springdoc vẫn tạo document từ application context của instance do build task khởi chạy. Các bean, profile, property, customizer và dependency runtime đều có thể tác động tới kết quả.

Điều này hữu ích vì file export đi qua cùng cơ chế tạo tài liệu mà ứng dụng sử dụng khi chạy. Nó cũng có nghĩa cấu hình export phải được kiểm soát để tránh tạo contract từ một profile khác với cấu hình phát hành dự kiến.

## 3. Những yếu tố làm tài liệu build và runtime khác nhau

| Yếu tố | Ảnh hưởng tới OpenAPI document |
|---|---|
| Spring profile | Có thể bật/tắt controller, bean, customizer hoặc group |
| Environment properties | Thay đổi `Info`, `servers`, path filter, media type hoặc endpoint docs |
| `@ConditionalOnProperty` / `@Profile` | Thay đổi bean tham gia application context |
| `GroupedOpenApi` | Thay đổi tập path và operation trong từng document |
| `OpenAPI` bean/customizer | Thay đổi metadata, security, server URL, schema hoặc operation |
| Request headers | Có thể ảnh hưởng locale, forwarded host/port hoặc authentication |
| Reverse proxy | Có thể làm server URL được suy ra khác nhau |
| Cache | Document được tính một lần và tái sử dụng theo cấu hình mặc định |
| Springdoc/library version | Có thể thay đổi cách suy ra schema và operation |
| API docs enabled/security | Có thể khiến endpoint export hoặc runtime không truy cập được |

Ví dụ, profile build có thể tắt kết nối tới database thật để ứng dụng khởi động trong CI. Điều đó phù hợp nếu controller và contract không thay đổi. Nếu profile build vô tình loại một controller hoặc một `GroupedOpenApi`, file xuất ra sẽ không đại diện cho contract được phát hành.

Không nên dùng hai profile khác nhau mà không có lý do và kiểm thử đối chiếu. Nếu staging/production cần cấu hình `servers` khác nhau, hãy quyết định rõ phần nào là contract chung và phần nào là deployment metadata.

## 4. Cấu hình endpoint tài liệu runtime

Các property cơ bản:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
    enabled: true
  writer-with-default-pretty-printer: true
~~~

`springdoc.api-docs.path` đổi đường dẫn endpoint JSON. `springdoc.api-docs.enabled=false` tắt endpoint OpenAPI của ứng dụng. Nếu endpoint bị tắt trong profile production, build plugin vẫn có thể xuất artifact ở profile `openapi`, nhưng không thể tải document từ production qua endpoint đó.

Springdoc cũng hỗ trợ YAML qua suffix `.yaml`:

~~~text
/v3/api-docs.yaml
~~~

Với nhiều document, khai báo group bằng `GroupedOpenApi` hoặc `springdoc.group-configs`. Tên group phải ổn định vì nó trở thành một phần của URL export và tên artifact:

~~~yaml
springdoc:
  group-configs:
    - group: public
      display-name: Public API
      paths-to-match:
        - /api/public/**
    - group: admin
      display-name: Admin API
      paths-to-match:
        - /api/admin/**
~~~

Document tương ứng mặc định nằm tại `/v3/api-docs/public` và `/v3/api-docs/admin`.

## 5. Chọn profile riêng cho lần export

Có thể tạo profile `openapi` để khởi động application trong build:

~~~yaml
# application-openapi.yml
spring:
  datasource:
    url: jdbc:h2:mem:openapi

springdoc:
  api-docs:
    enabled: true
~~~

Profile này có thể dùng database test, mock service hoặc dependency thay thế để ứng dụng khởi động trong CI. Tuy nhiên, không nên loại controller, thay đổi path, response schema hoặc security metadata chỉ để export dễ hơn.

Một quy tắc hữu ích:

- Có thể thay thế hạ tầng bên ngoài nếu nó không làm thay đổi contract.
- Không thay đổi tập endpoint, method, request/response schema hoặc operation metadata so với cấu hình phát hành.
- Nếu contract phụ thuộc profile, phải export và validate từng profile như các artifact riêng.
- Ghi rõ profile và property đã dùng vào metadata của build hoặc CI artifact record.

Nếu server URL thay đổi theo môi trường, có thể dùng server configuration rõ ràng hoặc forwarded headers được kiểm soát. Không để một hostname nội bộ của CI vô tình trở thành server URL trong file phát hành.

## 6. Xuất OpenAPI bằng Maven

`springdoc-openapi-maven-plugin` làm việc cùng `spring-boot-maven-plugin`. Spring Boot Maven plugin khởi động ứng dụng ở pha `pre-integration-test`; Springdoc plugin gọi endpoint và ghi file ở pha `integration-test`; ứng dụng được yêu cầu dừng ở pha `post-integration-test`.

Ví dụ cấu hình trong `pom.xml`:

~~~xml
<properties>
    <springdoc.maven-plugin.version>PLUGIN_VERSION</springdoc.maven-plugin.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <jvmArguments>
                    -Dspring.application.admin.enabled=true
                </jvmArguments>
                <arguments>
                    <argument>--spring.profiles.active=openapi</argument>
                </arguments>
            </configuration>
            <executions>
                <execution>
                    <id>start-openapi-application</id>
                    <phase>pre-integration-test</phase>
                    <goals>
                        <goal>start</goal>
                    </goals>
                </execution>
                <execution>
                    <id>stop-openapi-application</id>
                    <phase>post-integration-test</phase>
                    <goals>
                        <goal>stop</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-maven-plugin</artifactId>
            <version>${springdoc.maven-plugin.version}</version>
            <executions>
                <execution>
                    <id>export-openapi</id>
                    <phase>integration-test</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <apiDocsUrl>
                    http://localhost:8080/v3/api-docs
                </apiDocsUrl>
                <outputDir>
                    ${project.build.directory}/openapi
                </outputDir>
                <outputFileName>openapi.json</outputFileName>
                <attachArtifact>true</attachArtifact>
                <attachArtifactClassifier>openapi</attachArtifactClassifier>
                <failOnError>true</failOnError>
                <timeout>60</timeout>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Thay `PLUGIN_VERSION` bằng version plugin được quản lý trong dự án. Ví dụ dùng placeholder để tránh ghim version plugin cũ vào một dự án có Spring Boot/Springdoc khác.

Chạy:

~~~bash
./mvnw verify
~~~

File mặc định trong ví dụ được ghi tại:

~~~text
target/openapi/openapi.json
~~~

`attachArtifact=true` gắn file với Maven artifact bằng classifier `openapi`, để có thể install/deploy cùng binary. Nếu chỉ muốn dùng nội bộ trong CI, có thể để `attachArtifact=false` và upload file như một build artifact riêng.

### 6.1. Các tham số Maven thường dùng

| Tham số | Ý nghĩa |
|---|---|
| `apiDocsUrl` | URL JSON/YAML cần tải |
| `outputDir` | Thư mục ghi file |
| `outputFileName` | Tên file |
| `attachArtifact` | Gắn OpenAPI file vào Maven artifact |
| `attachArtifactClassifier` | Classifier của file được gắn |
| `headers` | HTTP headers gửi tới endpoint, ví dụ Authorization |
| `timeout` | Connect/read timeout |
| `skip` | Bỏ qua goal export |
| `failOnError` | Làm build thất bại nếu không tải/ghi được document |

Plugin mặc định có `failOnError=false`. Trên CI nên đặt `true`; nếu không, job có thể tiếp tục dù file không được tạo. Không dùng `skip=true` trong job phát hành contract.

### 6.2. Gửi header xác thực an toàn

Nếu endpoint tài liệu cần authentication, plugin hỗ trợ gửi header:

~~~xml
<headers>
    <Authorization>Bearer ${env.OPENAPI_EXPORT_TOKEN}</Authorization>
</headers>
~~~

Không ghi token thật vào `pom.xml`, file YAML được commit hoặc log CI. Cấp token qua secret store của CI và chỉ cho job export quyền đọc tài liệu cần thiết.

### 6.3. Xuất YAML

Đổi URL và tên file:

~~~xml
<apiDocsUrl>
    http://localhost:8080/v3/api-docs.yaml
</apiDocsUrl>
<outputFileName>openapi.yaml</outputFileName>
~~~

Nội dung được lưu theo định dạng endpoint trả về. Nếu muốn JSON dễ đọc, bật `springdoc.writer-with-default-pretty-printer=true` trong profile export.

### 6.4. Xuất nhiều group

Mỗi group cần một execution với URL và tên file riêng:

~~~xml
<executions>
    <execution>
        <id>export-public-api</id>
        <phase>integration-test</phase>
        <goals>
            <goal>generate</goal>
        </goals>
        <configuration>
            <apiDocsUrl>
                http://localhost:8080/v3/api-docs/public
            </apiDocsUrl>
            <outputFileName>openapi-public.json</outputFileName>
            <attachArtifact>true</attachArtifact>
            <attachArtifactClassifier>openapi-public</attachArtifactClassifier>
            <failOnError>true</failOnError>
        </configuration>
    </execution>
    <execution>
        <id>export-admin-api</id>
        <phase>integration-test</phase>
        <goals>
            <goal>generate</goal>
        </goals>
        <configuration>
            <apiDocsUrl>
                http://localhost:8080/v3/api-docs/admin
            </apiDocsUrl>
            <outputFileName>openapi-admin.json</outputFileName>
            <attachArtifact>true</attachArtifact>
            <attachArtifactClassifier>openapi-admin</attachArtifactClassifier>
            <failOnError>true</failOnError>
        </configuration>
    </execution>
</executions>
~~~

Nếu project dùng nhiều group, hãy kiểm tra tất cả group trong CI. Một lần export default `/v3/api-docs` không chứng minh các group public/admin đều được tạo đúng.

## 7. Xuất OpenAPI bằng Gradle

Springdoc cung cấp plugin `org.springdoc.openapi-gradle-plugin`. Plugin cần ứng dụng có Spring Boot plugin và dependency Springdoc API để endpoint tài liệu được phục vụ.

Ví dụ Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version libs.versions.springBoot.get()
    id("org.springdoc.openapi-gradle-plugin")
}

openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.json")
    waitTimeInSeconds.set(60)

    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

Khai báo version plugin trong `pluginManagement` hoặc version catalog theo chuẩn của dự án. Plugin có task:

~~~bash
./gradlew generateOpenApiDocs
~~~

File mặc định được ghi vào `build/openapi.json`; ví dụ trên đổi thành `build/openapi/openapi.json`.

Plugin Gradle khởi chạy ứng dụng theo cấu hình `bootRun`, tải OpenAPI document và dừng ứng dụng. `customBootRun` cho phép đặt profile, JVM arguments, system properties hoặc environment variables riêng cho lần export.

### 7.1. Xuất group bằng Gradle

`groupedApiMappings` ánh xạ URL của group sang tên file:

~~~kotlin
openApi {
    groupedApiMappings.set(
        mapOf(
            "http://localhost:8080/v3/api-docs/public" to
                "openapi-public.json",
            "http://localhost:8080/v3/api-docs/admin" to
                "openapi-admin.json"
        )
    )
}
~~~

Khi cấu hình `groupedApiMappings`, `apiDocsUrl` và `outputFileName` đơn lẻ không còn được dùng. Hãy kiểm tra từng file output sau task.

### 7.2. Xuất YAML và headers

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs.yaml")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.yaml")
    requestHeaders.set(
        mapOf(
            "x-forwarded-host" to "api.example.test",
            "x-forwarded-proto" to "https"
        )
    )
}
~~~

Không gửi forwarded header tùy tiện. Chỉ dùng chúng khi cần mô phỏng đúng reverse proxy mà ứng dụng tin cậy, và bảo đảm cấu hình forwarded-header strategy của Spring Boot phù hợp.

### 7.3. Tương thích phiên bản build plugin

Build plugin chỉ gọi HTTP endpoint, nhưng ứng dụng được khởi chạy vẫn phải dùng cặp Spring Boot/Springdoc tương thích. Ma trận tương thích hiện hành của plugin Springdoc nêu:

| Spring Boot | Springdoc |
|---|---|
| 4.x | 3.x |
| 3.x | 2.x |
| 2.x và 1.x | 1.x |

Version của Maven/Gradle build plugin là một dependency riêng, không phải version của Springdoc runtime starter. Quản lý và pin cả hai version. Tài liệu plugin Maven nêu yêu cầu Maven 3.6.3+ và Java 8+; plugin Gradle yêu cầu Gradle 8.0+ và cần Spring Boot plugin cùng Java/Kotlin plugin trong build.

## 8. Giữ export profile gần với cấu hình phát hành

Một profile export có thể thay database hoặc external integration để build không phụ thuộc dịch vụ thật:

~~~yaml
# application-openapi.yml
spring:
  datasource:
    url: jdbc:h2:mem:openapi

springdoc:
  api-docs:
    enabled: true
~~~

Không cần tạo profile mới nếu profile mặc định đã đủ để khởi động. Nếu có profile riêng, cần ghi nhận rõ:

- Profile nào được kích hoạt khi export.
- Environment variables nào ảnh hưởng tới `OpenAPI` bean hoặc customizer.
- Các `@ConditionalOnProperty` và `@Profile` nào thay đổi controller/group.
- External service nào được thay thế bằng mock.
- Server URL nào được đưa vào document.

Nếu API group, controller hoặc OpenAPI configuration phụ thuộc profile, hãy export và validate từng profile như các artifact riêng. Một profile dùng để tắt dịch vụ bên ngoài có thể an toàn; profile làm mất endpoint hoặc thay đổi schema sẽ tạo ra contract khác.

Không nên thay response hoặc ẩn operation chỉ để build không cần khởi động một hệ thống phụ trợ. Hãy thay dependency hạ tầng ở tầng service bằng mock/test adapter trong khi giữ nguyên controller contract.

## 9. Quản lý server URL, proxy và cache

OpenAPI `servers` mô tả base URL mà client dùng để gọi API. Springdoc có thể suy ra server URL từ request hiện tại; nếu có server annotation/configuration rõ ràng, giá trị được khai báo sẽ được dùng.

Trong môi trường sau reverse proxy, request nội bộ có thể thấy host/port khác với URL public. Khi đó:

- Cấu hình forwarded headers đúng ở Spring Boot/proxy.
- Chỉ tin forwarded headers từ proxy tin cậy.
- Có thể gửi `x-forwarded-host`, `x-forwarded-port` hoặc `x-forwarded-proto` trong lần export nếu plugin cần mô phỏng request sau proxy.
- Kiểm tra `servers` trong file đã xuất và trong document runtime.

Springdoc cache OpenAPI document theo mặc định. Nếu server URL phải được tính lại theo từng request, chẳng hạn cùng ứng dụng được phục vụ sau nhiều proxy, có thể cấu hình:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Property tương ứng là `springdoc.cache.disabled=true`. Tắt cache chỉ khi thực sự cần document thay đổi theo request. Nếu contract không phụ thuộc host của request, một `servers` URL tường minh thường giúp artifact build ổn định hơn.

Locale cũng có thể ảnh hưởng nội dung mô tả. Nếu ứng dụng dùng `Accept-Language` để tạo document đa ngôn ngữ, chọn locale rõ ràng cho export và ghi locale đó vào metadata artifact. Không để locale mặc định trên máy runner quyết định nội dung contract.

## 10. Làm cho artifact có thể tái lập

Hai lần export cùng commit nên tạo document tương đương về mặt hợp đồng. Để đạt điều đó:

1. Pin version Spring Boot, Springdoc, plugin Maven/Gradle và dependency quản lý schema.
2. Dùng cùng profile export và cùng tập property.
3. Giữ ổn định `GroupedOpenApi`, package/path filters và customizers.
4. Khai báo `info.version` từ một nguồn version duy nhất của build.
5. Dùng server URL tường minh nếu hostname không phải một phần của artifact.
6. Kiểm soát locale và `Accept-Language` nếu mô tả có i18n.
7. Giữ ổn định thứ tự output khi cần review diff; Springdoc có `springdoc.writer-with-order-by-keys`.
8. Không đưa timestamp hoặc dữ liệu ngẫu nhiên vào description, extension hay schema.
9. Ghi lại commit SHA, application version, profile và build number bên ngoài hoặc cùng metadata artifact.

Pretty-print giúp review file, còn deterministic key ordering giúp giảm diff do thứ tự property. Cả hai không thay thế semantic diff: thay đổi một schema, path, security requirement hoặc server URL vẫn cần được review.

Nếu build plugin Gradle đánh dấu task up-to-date, nó có thể không khởi chạy ứng dụng lại khi classpath, application settings và cấu hình export không đổi. Đảm bảo các property môi trường ảnh hưởng document được khai báo như task input hoặc chủ động làm task chạy lại khi những giá trị đó thay đổi.

## 11. Kiểm tra artifact sau khi export

Không coi việc file xuất hiện là bằng chứng duy nhất. Sau export, cần:

- Xác nhận file không rỗng và đúng định dạng JSON/YAML.
- Parse document bằng OpenAPI parser hoặc validator.
- Lint các quy tắc naming, operationId, tag, security và schema của dự án.
- Kiểm tra `openapi`, `info`, `servers`, `paths` và `components`.
- Xác minh tất cả group file được tạo.
- So sánh với baseline của release trước bằng semantic diff.
- Chặn build khi có lỗi tải, parse, lint hoặc thay đổi breaking chưa được duyệt.

Ví dụ kiểm tra nhanh JSON:

~~~bash
test -s target/openapi/openapi.json
jq -e '.openapi and .info.title and (.paths | type == "object")' \
  target/openapi/openapi.json
~~~

Lệnh `jq` ở đây chỉ kiểm tra các trường nền tảng. Nó không thay thế OpenAPI validator vì chưa kiểm tra đầy đủ tham chiếu, schema và quy tắc đặc tả.

## 12. So sánh với document của ứng dụng đang triển khai

Khi ứng dụng đã triển khai, có thể truy xuất document runtime nếu endpoint được bật và caller có quyền:

~~~bash
curl --fail --silent --show-error \
  https://staging.example.com/v3/api-docs \
  -o deployed-openapi.json
~~~

Nếu dùng group:

~~~bash
curl --fail --silent --show-error \
  https://staging.example.com/v3/api-docs/public \
  -o deployed-openapi-public.json
~~~

Nếu endpoint yêu cầu authentication, dùng credential được cấp qua secret store của CI. Không lưu bearer token trong command history, file được commit hoặc artifact.

Đối chiếu artifact build với document runtime theo các nhóm:

| Phần cần so sánh | Điều cần xác nhận |
|---|---|
| `paths` và HTTP methods | Không mất hoặc thêm operation ngoài dự kiến |
| `operationId` | ID ổn định và duy nhất |
| Parameters/request body | Tên, required, schema và content type khớp |
| Responses | Status code, headers, media type và schema khớp |
| `components.schemas` | Không mất component hoặc thay đổi constraint ngoài ý muốn |
| `security` | Authentication requirement đúng |
| `servers` | URL base phù hợp với môi trường |
| Group documents | Tập operation public/admin đúng với mục đích group |

Không so sánh file dạng text rồi kết luận mọi khác biệt đều là contract drift. Thứ tự key hoặc pretty-print có thể khác mà không làm thay đổi ý nghĩa. Dùng OpenAPI-aware semantic diff, sau đó review những thay đổi có ý nghĩa.

### 12.1. Phân loại khác biệt

Một số khác biệt thường chỉ thuộc deployment metadata:

- Hostname hoặc port trong `servers`.
- Context path do ingress/gateway gắn thêm.
- URL public và internal khác nhau.

Một số khác biệt ảnh hưởng trực tiếp contract:

- Path hoặc HTTP method bị thêm/xóa.
- Request parameter, required flag hoặc schema thay đổi.
- Response code hoặc response schema thay đổi.
- Security requirement bị bỏ hoặc đổi.
- `operationId` hoặc tag thay đổi, có thể ảnh hưởng SDK và API portal.

Không tự động bỏ qua mọi khác biệt trong `servers`. Nếu file build được phát hành cho SDK generator, server URL cũng có thể được đóng gói vào client; hãy quyết định rõ server nào thuộc artifact và server nào được cấu hình khi triển khai.

## 13. Khi production không expose /v3/api-docs

Một số ứng dụng tắt endpoint tài liệu trên production bằng:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Đây là lựa chọn triển khai hợp lệ khi contract artifact đã được phát hành qua API portal hoặc artifact repository. Tuy nhiên, khi endpoint runtime bị tắt, pipeline không thể dùng nó để chứng minh document đang triển khai giống artifact build.

Trong trường hợp đó:

- Lưu artifact OpenAPI gắn với đúng image/tag/commit đã deploy.
- Kiểm tra image digest hoặc release metadata để biết instance chạy đúng binary nào.
- Chạy smoke test vào các operation quan trọng.
- Kiểm tra contract trong staging trước khi promote.
- Nếu cần kiểm tra document thực tế, expose endpoint trong staging hoặc một kênh quản trị được bảo vệ, không nhất thiết công khai ở production.

Artifact build cho biết ứng dụng được mô tả thế nào theo cấu hình export. Smoke test runtime xác nhận ứng dụng triển khai có hành vi phù hợp. Hai bằng chứng này bổ sung cho nhau.

## 14. CI pipeline cho OpenAPI artifact

Một pipeline tham khảo:

~~~text
Checkout exact commit
        |
        v
Resolve pinned dependencies
        |
        v
Compile and package application
        |
        v
Start application with openapi profile
        |
        v
Fetch default and grouped OpenAPI documents
        |
        v
Stop the build application
        |
        v
Parse and lint each document
        |
        v
Semantic diff against released baseline
        |
        v
Review breaking / security-sensitive changes
        |
        v
Attach or publish versioned OpenAPI artifacts
        |
        v
Deploy same application image to staging
        |
        v
Fetch runtime docs or run runtime smoke tests
        |
        v
Compare runtime and build contract
~~~

Trong CI:

- Bật `failOnError=true` cho Maven plugin.
- Không bỏ qua task export khi job phát hành contract.
- Lưu OpenAPI file như artifact có version và liên kết commit.
- Kiểm tra tất cả group, không chỉ default document.
- Chạy semantic diff trước khi phát hành SDK hoặc API portal.
- Không promote nếu staging có drift chưa được giải thích.

Maven plugin lưu ý rằng khi build thất bại trước pha stop, ứng dụng có thể vẫn chạy. Runner cần được dọn dẹp hoặc process phải được dừng trước lần build tiếp theo để tránh request export nhầm instance cũ. Gradle plugin cũng cần port trống và ứng dụng phải khởi động thành công trước timeout.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Build thành công nhưng không có file | `failOnError=false`, goal bị skip hoặc endpoint không truy cập được | Bật fail-on-error và kiểm tra log/task |
| File thiếu controller | Profile export không tạo bean/controller đó | So sánh profile và condition với cấu hình phát hành |
| Export nhầm document cũ | Một process cũ đang chiếm port | Dừng process, dùng port riêng và xác nhận startup log |
| Maven không dừng ứng dụng sau lỗi | Pha `post-integration-test` không được chạy khi build fail | Dọn process trong CI trước job tiếp theo |
| Gradle chờ quá lâu | Sai port/path hoặc app chưa sẵn sàng | Kiểm tra `apiDocsUrl`, tăng `waitTimeInSeconds` khi cần |
| Group file không xuất hiện | Sai group name hoặc URL | Kiểm tra `/v3/api-docs/{group}` và group config |
| Runtime `servers` khác build | Proxy/forwarded headers hoặc server annotations khác nhau | Chuẩn hóa `servers` hoặc cấu hình proxy headers |
| Schema khác giữa các môi trường | Version dependency hoặc profile/customizer khác | Pin dependency và kiểm tra condition/property |
| Production không truy cập được docs | `springdoc.api-docs.enabled=false` hoặc Security chặn | Dùng artifact đã phát hành và smoke test runtime |
| File diff rất lớn nhưng API không đổi | JSON key order, formatter hoặc locale khác | Chuẩn hóa output và dùng semantic diff |
| CI không tải được endpoint có bảo vệ | Thiếu Authorization header hoặc token hết hạn | Cấp secret và truyền qua plugin header config |
| Artifact có URL localhost | Export từ server URL được suy ra trong build | Khai báo `servers` phù hợp hoặc xử lý server metadata theo môi trường |

## 16. Bài thực hành tổng hợp

Thiết lập một project Spring Boot có public và admin API:

1. Tạo hai `GroupedOpenApi` tên `public` và `admin`.
2. Xác nhận runtime endpoint `/v3/api-docs/public` và `/v3/api-docs/admin`.
3. Cấu hình profile `openapi` để ứng dụng khởi động trong CI mà không cần external service thật.
4. Dùng Maven plugin hoặc Gradle plugin để xuất hai document thành hai file.
5. Bật fail-on-error và kiểm tra file không rỗng.
6. Parse/lint cả hai file.
7. Lưu artifact kèm commit SHA, application version và profile.
8. Tạo một thay đổi có chủ đích trong `operationId` hoặc response schema để quan sát semantic diff.
9. Deploy đúng image đã build lên staging.
10. Truy xuất document runtime nếu endpoint được phép truy cập.
11. So sánh paths, methods, operationId, schemas, security và servers.
12. Tắt endpoint docs trong production profile, xác nhận artifact build vẫn được publish và smoke test API vẫn chạy.
13. Thử build export thất bại để xác minh CI phát hiện lỗi và dọn process.

### Tiêu chí hoàn thành

- [ ] Phân biệt được runtime OpenAPI document và build-exported artifact.
- [ ] Giải thích được build plugin khởi chạy ứng dụng rồi gọi HTTP endpoint.
- [ ] Xuất được JSON và YAML bằng Maven hoặc Gradle.
- [ ] Xuất được từng `GroupedOpenApi` thành file riêng.
- [ ] Profile export không làm thay đổi contract ngoài dự kiến.
- [ ] File được parse/lint và semantic diff với baseline.
- [ ] Artifact có version, commit và thông tin cấu hình export.
- [ ] CI thất bại nếu không tải hoặc ghi được document.
- [ ] Biết xử lý port conflict và process còn chạy sau build lỗi.
- [ ] So sánh được artifact build với document runtime trên staging.
- [ ] Có quy trình khi production tắt `/v3/api-docs`.
- [ ] Không phát hành SDK hoặc API portal từ một artifact chưa được review.

## Tiếp tục học

Sau bài này, hãy kết hợp export artifact với contract testing, backward compatibility và phân phối tài liệu. Một OpenAPI file chỉ có giá trị khi biết nó được sinh từ commit, dependency, profile và group nào; đối chiếu nó với ứng dụng triển khai giúp phát hiện sớm cấu hình sai hoặc contract drift trước khi client gặp lỗi.

## Tài liệu tham khảo

- [Springdoc FAQ – Export JSON/YAML during build](https://springdoc.org/faq.html)
- [springdoc-openapi Maven plugin](https://github.com/springdoc/springdoc-openapi-maven-plugin)
- [springdoc-openapi Gradle plugin](https://github.com/springdoc/springdoc-openapi-gradle-plugin)
- [Springdoc Core Properties Reference](https://springdoc.org/core-properties.html)
- [Springdoc FAQ – Multiple OpenAPI definitions and groups](https://springdoc.org/faq.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
