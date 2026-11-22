# Tích hợp Gradle plugin và các tác vụ chạy ứng dụng, sinh đặc tả

springdoc-openapi có thể phục vụ OpenAPI Description trực tiếp từ ứng dụng Spring Boot tại endpoint như **/v3/api-docs**. Khi cần lưu tài liệu thành file trong quá trình build, có thể dùng **springdoc-openapi-gradle-plugin**. Plugin khởi chạy ứng dụng Spring Boot, gọi endpoint tài liệu, ghi JSON hoặc YAML vào thư mục build rồi dừng ứng dụng.

Task chính của plugin là **generateOpenApiDocs**. Task này giúp đưa tài liệu được sinh từ ứng dụng đang chạy vào quy trình build và CI: có thể lưu artifact, kiểm tra thay đổi hợp đồng, chạy validator hoặc chuyển tài liệu cho client generator.

Điểm cần phân biệt là plugin Gradle không tự phân tích controller để tạo schema. Ứng dụng vẫn cần dependency springdoc-openapi để cung cấp endpoint tài liệu. Gradle plugin chỉ khởi động ứng dụng và tải nội dung từ endpoint đó.

## 1. Vai trò của plugin trong build

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Gradle build"] --> B["Resolve application runtime classpath"]
    B --> C["Start Spring Boot application"]
    C --> D["Wait until application is ready"]
    D --> E["GET /v3/api-docs or grouped URL"]
    E --> F["Write OpenAPI JSON/YAML to outputDir"]
    F --> G["Stop application"]
    G --> H["Validate / diff / publish / generate client"]
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Spring Boot application | Khởi tạo controller, router, security, configuration và runtime environment |
| springdoc-openapi starter | Phân tích metadata Spring và phục vụ OpenAPI Description |
| springdoc-openapi-gradle-plugin | Khởi động ứng dụng, gọi API docs endpoint và ghi file |
| Gradle task | Điều phối thời điểm chạy plugin trong build |
| CI pipeline | Chạy build, lưu artifact, validate, so sánh hợp đồng hoặc phát hành tài liệu |

Vì plugin lấy tài liệu qua HTTP từ ứng dụng đang chạy, kết quả phản ánh cấu hình runtime được dùng trong lần khởi chạy đó. Profile, environment variable, command-line argument, database seed hoặc feature flag có thể làm thay đổi các endpoint và schema được công bố.

## 2. Dependency cần có

Ứng dụng phải có springdoc starter phù hợp với stack web để endpoint OpenAPI tồn tại. Ví dụ ứng dụng Spring MVC dùng starter API:

~~~kotlin
val springdocVersion = providers.gradleProperty("springdocVersion").get()

dependencies {
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-api:" + springdocVersion
    )
}
~~~

Trong ví dụ, springdocVersion là Gradle property cần được khai báo trong gradle.properties hoặc cung cấp qua version catalog. Giá trị phải thuộc nhánh springdoc tương thích với Spring Boot của ứng dụng.

Với ứng dụng WebFlux, dùng starter WebFlux tương ứng:

~~~kotlin
dependencies {
    implementation(
        "org.springdoc:springdoc-openapi-starter-webflux-api:" + springdocVersion
    )
}
~~~

Đặt version trong gradle.properties hoặc version catalog và chọn phiên bản springdoc tương thích với Spring Boot đang dùng. Ma trận phổ biến của dự án springdoc là Spring Boot 4.x đi với springdoc 3.x, Spring Boot 3.x đi với springdoc 2.x và Spring Boot 2.x đi với springdoc 1.x. Kiểm tra ma trận của đúng release trước khi nâng cấp.

Nếu cần giao diện Swagger UI trong ứng dụng, có thể dùng starter có hậu tố webmvc-ui hoặc webflux-ui. Nếu pipeline chỉ cần file OpenAPI, starter API thường là đủ và không cần đóng gói giao diện người dùng.

## 3. Thêm Gradle plugin

Plugin ID là **org.springdoc.openapi-gradle-plugin**. Ví dụ Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("org.springdoc.openapi-gradle-plugin") version "2.1.0"
}
~~~

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'org.springdoc.openapi-gradle-plugin' version '2.1.0'
}
~~~

Version 3.5.16 của Spring Boot và 2.1.0 của Gradle plugin trong ví dụ là các version minh họa cho cấu hình Spring Boot 3.x. Với dự án thực tế, thay version Spring Boot theo nền tảng đang dùng và kiểm tra phiên bản plugin trên Gradle Plugin Portal.

Ở thời điểm viết bài, plugin portal công bố plugin 2.1.0. Nhánh hiện hành yêu cầu Gradle 8.0 trở lên và được kiểm thử tới Gradle 9.8. Plugin hỗ trợ build dùng Kotlin DSL hoặc Groovy DSL. Plugin cần Spring Boot Gradle plugin cùng Java plugin hoặc Kotlin plugin để có thể khởi chạy ứng dụng với classpath của task bootRun.

Từ phiên bản 2.1, plugin không còn tự áp dụng Spring Boot Gradle plugin. Vì vậy, phải khai báo org.springframework.boot rõ ràng trong khối plugins của dự án.

## 4. Task generateOpenApiDocs hoạt động thế nào?

Sau khi áp dụng plugin, chạy:

~~~bash
./gradlew generateOpenApiDocs
~~~

Trên Windows:

~~~powershell
.\gradlew.bat generateOpenApiDocs
~~~

Task thực hiện các bước:

1. Chuẩn bị runtime classpath và cấu hình khởi chạy của ứng dụng.
2. Kiểm tra port của apiDocsUrl có bị một tiến trình khác chiếm hay không.
3. Khởi chạy Spring Boot application ở tiến trình nền.
4. Chờ ứng dụng sẵn sàng phục vụ endpoint tài liệu.
5. Gửi HTTP request tới apiDocsUrl hoặc từng URL trong groupedApiMappings.
6. Ghi nội dung nhận được vào outputDir với tên file đã cấu hình.
7. Dừng ứng dụng sau khi tải tài liệu.

Mặc định, task lấy tài liệu tại:

~~~text
http://localhost:8080/v3/api-docs
~~~

File mặc định được ghi thành:

~~~text
build/openapi.json
~~~

Từ plugin 2.0, việc khởi chạy và dừng ứng dụng nằm bên trong generateOpenApiDocs. Các task forkedSpringBootRun và forkedSpringBootStop của nhánh 1.x đã bị loại bỏ. Không thêm dependency hoặc cấu hình cho các task cũ khi đang dùng plugin 2.x.

## 5. Cấu hình cơ bản bằng Kotlin DSL

Ví dụ cấu hình đầy đủ trong build.gradle.kts:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("catalog-openapi.json")
    waitTimeInSeconds.set(60)

    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

Sau khi chạy generateOpenApiDocs, file được tạo ở:

~~~text
build/openapi/catalog-openapi.json
~~~

Trong đó:

- **apiDocsUrl** là endpoint mà plugin tải OpenAPI Description.
- **outputDir** là thư mục chứa file kết quả.
- **outputFileName** là tên file được ghi.
- **waitTimeInSeconds** là thời gian tối đa plugin chờ ứng dụng khởi động và phục vụ endpoint.
- **customBootRun** tùy chỉnh cách ứng dụng được chạy riêng cho lần sinh tài liệu.

Các property đều có giá trị mặc định; chỉ cấu hình lại những giá trị cần thay đổi.

## 6. Cấu hình tương đương bằng Groovy DSL

Trong build.gradle:

~~~groovy
openApi {
    apiDocsUrl = 'http://localhost:9090/v3/api-docs'
    outputDir = layout.buildDirectory.dir('openapi')
    outputFileName = 'catalog-openapi.json'
    waitTimeInSeconds = 60

    customBootRun {
        args = ['--spring.profiles.active=openapi']
    }
}
~~~

Kotlin DSL dùng các property setter như set(), còn Groovy DSL có thể gán trực tiếp. Không trộn cú pháp hai DSL trong cùng file build.

## 7. Các thuộc tính cấu hình chính

| Thuộc tính | Mặc định | Mục đích |
|---|---|---|
| apiDocsUrl | http://localhost:8080/v3/api-docs | URL tải tài liệu OpenAPI |
| outputDir | build | Thư mục ghi file |
| outputFileName | openapi.json | Tên file đầu ra |
| waitTimeInSeconds | 30 | Thời gian chờ ứng dụng sẵn sàng |
| groupedApiMappings | Không có | Ánh xạ nhiều URL group tới tên file riêng |
| requestHeaders | Không có | HTTP header gửi khi gọi API docs endpoint |
| trustStore | Không có | Trust store chứa chứng thư tin cậy khi gọi HTTPS |
| trustStorePassword | Không có | Mật khẩu mở trust store |
| customBootRun | Cấu hình bootRun | Tùy chỉnh cách khởi chạy ứng dụng để sinh tài liệu |

Nếu ứng dụng khởi động chậm do migration, khởi tạo cache hoặc kết nối dependency, tăng waitTimeInSeconds. Nếu chờ lâu vẫn timeout, cần kiểm tra log khởi động và URL endpoint thay vì chỉ tăng thời gian chờ vô hạn.

## 8. Sinh file YAML thay vì JSON

Plugin chọn định dạng dựa trên URL tài liệu. Nếu apiDocsUrl kết thúc bằng .yaml, nội dung được ghi dưới dạng YAML:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs.yaml")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.yaml")
}
~~~

Tương đương Groovy:

~~~groovy
openApi {
    apiDocsUrl = 'http://localhost:8080/v3/api-docs.yaml'
    outputDir = layout.buildDirectory.dir('openapi')
    outputFileName = 'openapi.yaml'
}
~~~

Với JSON, plugin pretty-print nội dung trước khi ghi. Với YAML, plugin ghi nội dung YAML mà ứng dụng phục vụ. Không đổi đuôi file thành .yaml nếu URL vẫn trả JSON; đuôi file và định dạng thực tế phải thống nhất.

## 9. Dùng profile riêng cho tài liệu

Tài liệu có thể thay đổi theo Spring profile. Ví dụ, profile openapi có thể:

- Dùng database test hoặc dữ liệu seed ổn định.
- Tắt tích hợp tới hệ thống bên ngoài.
- Thay email/SMS gateway bằng adapter giả lập.
- Cấu hình server URL, context path hoặc security phù hợp môi trường sinh tài liệu.
- Bật endpoint hoặc nhóm API chỉ được công bố trong profile tài liệu nếu đó là chủ đích.

Cấu hình profile qua customBootRun:

~~~kotlin
openApi {
    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

Ứng dụng được chạy với các thiết lập bootRun mặc định. Các thuộc tính được khai báo trong customBootRun sẽ thay thế thuộc tính tương ứng của bootRun; những thuộc tính không khai báo tiếp tục lấy từ bootRun.

Hãy giữ profile sinh tài liệu gần với cấu hình triển khai thực tế. Nếu profile openapi tắt một nhóm controller hoặc bật thêm endpoint nội bộ, file OpenAPI tạo ra có thể khác hợp đồng production. Nên ghi rõ mục tiêu và phạm vi của profile.

## 10. Tùy chỉnh JVM, environment và working directory

customBootRun hỗ trợ các thuộc tính khởi chạy thường dùng:

| Thuộc tính | Ví dụ mục đích |
|---|---|
| args | Truyền --spring.profiles.active=openapi hoặc --server.port=9090 |
| jvmArgs | Thiết lập heap hoặc JVM option |
| systemProperties | Truyền system property cho Spring Environment |
| environment | Truyền environment variable |
| mainClass | Chọn main class cần chạy |
| classpath | Chọn runtime classpath |
| workingDir | Chọn thư mục làm việc |

Ví dụ Kotlin DSL:

~~~kotlin
openApi {
    customBootRun {
        args.set(
            listOf(
                "--spring.profiles.active=openapi",
                "--server.port=9090"
            )
        )
        jvmArgs.set(listOf("-Xms256m", "-Xmx1g"))
        environment.put("APP_MODE", "openapi-generation")
    }
}
~~~

Nếu không cấu hình customBootRun, plugin sử dụng thiết lập của task bootRun. Ứng dụng chạy từ project directory và dùng Java toolchain của bootRun. Điều này giúp ứng dụng tìm được file cấu hình hoặc compose.yaml tương đối theo dự án.

## 11. Sinh nhiều tài liệu theo GroupedOpenApi

Nếu ứng dụng có nhiều group, dùng groupedApiMappings để tải mỗi tài liệu vào một file riêng:

~~~kotlin
openApi {
    outputDir.set(layout.buildDirectory.dir("openapi"))
    groupedApiMappings.set(
        mapOf(
            "http://localhost:8080/v3/api-docs/public" to "openapi-public.json",
            "http://localhost:8080/v3/api-docs/admin" to "openapi-admin.json",
            "http://localhost:8080/v3/api-docs/partner" to "openapi-partner.json"
        )
    )
}
~~~

Ví dụ Groovy DSL:

~~~groovy
openApi {
    outputDir = layout.buildDirectory.dir('openapi')
    groupedApiMappings = [
        'http://localhost:8080/v3/api-docs/public' : 'openapi-public.json',
        'http://localhost:8080/v3/api-docs/admin' : 'openapi-admin.json',
        'http://localhost:8080/v3/api-docs/partner' : 'openapi-partner.json'
    ]
}
~~~

Kết quả:

~~~text
build/openapi/openapi-public.json
build/openapi/openapi-admin.json
build/openapi/openapi-partner.json
~~~

Khi groupedApiMappings được cấu hình, plugin dùng các URL và tên file trong map; apiDocsUrl và outputFileName bị bỏ qua. outputDir vẫn là thư mục chung cho các file kết quả.

Mỗi URL cần trỏ tới group thực sự được springdoc công bố. Nếu đổi group name hoặc springdoc.api-docs.path, cập nhật map tương ứng.

## 12. Gửi request header khi tải tài liệu

Plugin hỗ trợ requestHeaders để gửi HTTP header khi gọi apiDocsUrl. Điều này hữu ích khi:

- API docs endpoint được bảo vệ bằng Basic/Bearer authentication.
- Cần gửi forwarded host/port để OpenAPI tạo server URL công khai.
- Reverse proxy hoặc môi trường staging yêu cầu header định tuyến.

Ví dụ gửi forwarded headers:

~~~kotlin
openApi {
    requestHeaders.set(
        mapOf(
            "x-forwarded-host" to "api.example.com",
            "x-forwarded-port" to "443"
        )
    )
}
~~~

Để forwarded headers ảnh hưởng tới server URL được sinh, ứng dụng cần cấu hình server.forward-headers-strategy=framework và chỉ tin header đến từ proxy hoặc nguồn build được kiểm soát. Không gửi header giả mạo từ môi trường không đáng tin.

Nếu docs endpoint cần Authorization, có thể cấu hình header tương ứng nhưng không hard-code token trong build.gradle hoặc commit token vào repository. Lấy credential từ CI secret store hoặc biến môi trường và không in giá trị ra log.

## 13. Gọi endpoint HTTPS với trust store riêng

Nếu ứng dụng chỉ phục vụ HTTPS bằng chứng thư nội bộ hoặc CA riêng mà JVM chưa tin cậy, plugin có thể dùng trust store:

~~~bash
keytool -import -noprompt -alias api-ca -file ca.crt -keystore truststore.p12 -deststoretype PKCS12 -storepass changeit
~~~

Lệnh trên là ví dụ minh họa cho trust store dùng trong môi trường test. Không dùng mật khẩu ví dụ trong production; lưu mật khẩu thực trong secret store.

Kotlin DSL có thể cấu hình:

~~~kotlin
openApi {
    apiDocsUrl.set("https://localhost:9443/v3/api-docs")
    trustStore.set("config/truststore.p12")
    trustStorePassword.set(
        providers.environmentVariable("OPENAPI_TRUSTSTORE_PASSWORD")
            .map { it.toCharArray() }
    )
}
~~~

Đường dẫn trust store phải tồn tại trên máy chạy Gradle. Đảm bảo chứng thư CA cần thiết nằm trong trust store và JVM có thể đọc file. Không tắt kiểm tra TLS hoặc dùng trust-all certificate manager chỉ để task chạy thành công.

## 14. Tích hợp task vào vòng đời build

Plugin cung cấp task generateOpenApiDocs. Có thể gọi trực tiếp trong CI hoặc gắn task vào một task build hiện có.

Chạy riêng:

~~~bash
./gradlew clean generateOpenApiDocs
~~~

Nếu muốn build phụ thuộc vào việc sinh tài liệu:

~~~kotlin
tasks.named("build") {
    dependsOn("generateOpenApiDocs")
}
~~~

Nếu muốn sinh tài liệu sau khi build:

~~~kotlin
tasks.named("build") {
    finalizedBy("generateOpenApiDocs")
}
~~~

Hai cách có ngữ nghĩa khác nhau:

- dependsOn yêu cầu generateOpenApiDocs hoàn tất như một dependency trước khi task build hoàn thành.
- finalizedBy chạy task sinh tài liệu như finalizer sau task build.

Chỉ gắn vào build khi mọi lần build đều có thể khởi chạy ứng dụng và các dependency cần thiết. Trong dự án lớn, thường tốt hơn khi tạo một CI stage riêng để chỉ sinh tài liệu ở nhánh hoặc workflow cần kiểm tra hợp đồng.

Không giả định plugin tự chạy ở mọi lần gradle build. Nếu không gắn task vào lifecycle, cần gọi generateOpenApiDocs tường minh.

## 15. Tính up-to-date và configuration cache

Plugin hiện hành khai báo input từ classpath và cấu hình khởi chạy ứng dụng, bao gồm main class, arguments, JVM arguments, system properties, Java toolchain và cấu hình openApi. Khi các input không thay đổi và output còn hợp lệ, Gradle có thể đánh dấu task UP-TO-DATE và không khởi chạy ứng dụng lại.

Plugin hỗ trợ Gradle configuration cache. Có thể kiểm tra bằng:

~~~bash
./gradlew generateOpenApiDocs --configuration-cache
~~~

Nếu thay đổi profile, system property, classpath, main class hoặc openApi settings, task có thể phải chạy lại và tải tài liệu mới. Khi tài liệu không đổi nhưng task vẫn chạy, xem lại input/output của task và cấu hình có thay đổi hay không.

Không xóa build cache chỉ để ép task chạy trước khi xác định input nào đang khiến Gradle đánh giá task up-to-date.

## 16. Sử dụng Testcontainers hoặc test application

Một số API cần database hoặc service test để khởi động đúng. Có thể chọn test main class và test runtime classpath trong customBootRun:

~~~kotlin
openApi {
    customBootRun {
        mainClass.set("com.example.TestApplication")
        classpath.from(
            sourceSets.main.get().runtimeClasspath,
            sourceSets.test.get().runtimeClasspath
        )
    }
}
~~~

Cách này phù hợp khi TestApplication khởi tạo môi trường test, Testcontainers hoặc dữ liệu cần thiết để tài liệu phản ánh API. Cần bảo đảm test application có cấu hình springdoc và endpoint docs giống hợp đồng mong muốn.

Không mặc định test classpath luôn phù hợp để phát hành tài liệu. Test configuration có thể bật mock endpoint, dữ liệu giả hoặc route chỉ dùng cho kiểm thử. Hãy kiểm tra document sinh ra và ghi rõ nguồn runtime của nó.

## 17. Một pipeline CI mẫu

Pipeline có thể tách các bước build, sinh tài liệu, validate và lưu artifact:

~~~yaml
steps:
  - name: Build and test
    run: ./gradlew clean test

  - name: Generate OpenAPI
    run: ./gradlew generateOpenApiDocs

  - name: Validate OpenAPI
    run: npx @redocly/cli lint build/openapi.json

  - name: Upload OpenAPI artifact
    uses: actions/upload-artifact@v4
    with:
      name: openapi-description
      path: build/openapi.json
~~~

Đây là ví dụ workflow theo cú pháp GitHub Actions; trong CI khác, thay bước upload bằng cơ chế artifact tương ứng. Redocly CLI là validator/linter bên ngoài, không phải task tích hợp sẵn của springdoc Gradle plugin.

Nên kiểm tra:

- File OpenAPI có được tạo không?
- JSON/YAML có parse được không?
- Document có hợp lệ theo đúng OpenAPI version không?
- Có thay đổi path, method, schema, security hoặc response ngoài dự kiến không?
- Artifact có được lưu đúng build number/commit không?

## 18. So sánh hợp đồng với bản đã phát hành

Sau khi sinh file, có thể so sánh với bản OpenAPI đã lưu trong repository:

~~~bash
git diff --no-index -- api/openapi.json build/openapi.json
~~~

Nếu muốn CI thất bại khi tài liệu thay đổi nhưng chưa được cập nhật, có thể commit file baseline vào repository và dùng:

~~~bash
git diff --no-index --exit-code -- api/openapi.json build/openapi.json
~~~

Lệnh no-index so sánh hai file kể cả khi file sinh trong build chưa được Git track; exit code 1 cho biết hai file khác nhau. Đường dẫn và cách so sánh cần phù hợp với quy ước repository. So sánh văn bản trực tiếp có thể tạo diff lớn do thứ tự hoặc format. Với pipeline chuyên nghiệp, cân nhắc canonicalize JSON hoặc dùng công cụ breaking-change detection để phân biệt thay đổi tương thích và không tương thích.

Không tự động chấp nhận mọi diff. Thay đổi schema required, response code, security requirement hoặc xóa operation có thể ảnh hưởng consumer.

## 19. Tách generation khỏi publish

Sinh file OpenAPI và công bố tài liệu là hai thao tác khác nhau. Task generateOpenApiDocs chỉ tạo file local trong build output. Việc publish lên website, artifact repository, API portal hoặc Git repository cần bước riêng.

Một pipeline an toàn thường:

1. Sinh file từ commit đang build.
2. Validate OpenAPI document.
3. Kiểm tra diff và breaking change.
4. Lưu file như build artifact.
5. Chỉ publish khi branch, tag hoặc release policy cho phép.

Không đặt credential publish trong task generateOpenApiDocs nếu plugin chỉ cần đọc tài liệu từ ứng dụng. Dùng secret riêng cho bước publish và cấp quyền tối thiểu.

## 20. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy task generateOpenApiDocs | Plugin chưa được áp dụng hoặc plugin resolution lỗi | Kiểm tra plugins block và Gradle Plugin Portal |
| Ứng dụng thoát với exit code khác 0 | Spring Boot không khởi động được | Đọc log ứng dụng trong build output; kiểm tra profile, dependency và cấu hình |
| Không kết nối được apiDocsUrl sau thời gian chờ | Sai port/path hoặc ứng dụng khởi động lâu | Kiểm tra URL, port và tăng waitTimeInSeconds có kiểm soát |
| Port đã có tiến trình khác lắng nghe | Ứng dụng khác đang dùng port của apiDocsUrl | Dừng tiến trình cũ hoặc cấu hình server.port riêng cho docs |
| File không nằm ở vị trí mong đợi | outputDir hoặc outputFileName khác mặc định | Kiểm tra khối openApi và đường dẫn build output |
| File YAML nhưng nội dung là JSON | apiDocsUrl không kết thúc bằng .yaml | Dùng endpoint YAML và tên file .yaml |
| Group bị thiếu | groupedApiMappings dùng sai group URL | Kiểm tra /v3/api-docs/{group} và group name |
| 401/403 khi tải tài liệu | Endpoint docs được bảo vệ | Cấu hình requestHeaders từ secret store hoặc profile docs phù hợp |
| HTTPS handshake thất bại | JVM không tin CA của server | Cấu hình trustStore và trustStorePassword |
| Server URL sinh ra sai host/port | Thiếu forwarded headers hoặc strategy chưa đúng | Kiểm tra requestHeaders và server.forward-headers-strategy |
| Tài liệu khác production | Profile hoặc environment khi generation khác | Chuẩn hóa profile, config và dữ liệu runtime |
| Task luôn UP-TO-DATE | Input không thay đổi theo Gradle | Kiểm tra task inputs, output và cấu hình customBootRun |
| Task chạy lại ngoài ý muốn | Classpath, args hoặc property thay đổi | So sánh input của task và cấu hình build |
| Dùng plugin 2.x nhưng cấu hình task forked cũ | Đang áp dụng hướng dẫn 1.x | Xóa forkedSpringBootRun/forkedSpringBootStop và dùng generateOpenApiDocs |
| Plugin không tự áp dụng Spring Boot plugin | Hành vi từ phiên bản 2.1 trở đi | Khai báo org.springframework.boot trong plugins block |

## 21. Nâng cấp từ plugin 1.x lên 2.x

Nhánh 2.x thay đổi cách khởi chạy ứng dụng:

| Plugin 1.x | Plugin 2.x |
|---|---|
| Có forkedSpringBootRun và forkedSpringBootStop | Task generateOpenApiDocs tự khởi động và dừng ứng dụng |
| Dựa vào execfork plugin | Không cần cấu hình execfork thủ công |
| Có thể cần workaround workingDir hoặc dependency task | Ứng dụng chạy từ project directory và task tự khai báo dependency cần thiết |
| Cấu hình tương thích configuration cache có thể cần xử lý riêng | Plugin hiện hành hỗ trợ configuration cache |
| Plugin có thể tự áp dụng Spring Boot plugin ở bản cũ | Từ 2.1, build phải áp dụng Spring Boot plugin rõ ràng |

Khi nâng cấp:

1. Cập nhật plugin version trong plugins block.
2. Khai báo Spring Boot Gradle plugin tường minh.
3. Xóa cấu hình forkedSpringBootRun và forkedSpringBootStop.
4. Xóa dependency execfork nếu chỉ dùng cho plugin cũ.
5. Chuyển cấu hình profile, args, JVM và system properties vào customBootRun.
6. Chạy generateOpenApiDocs và kiểm tra file đầu ra.
7. Bật configuration cache và xác minh build trong CI.

Không sao chép nguyên cấu hình 1.x sang 2.x. Đọc migration guide của release đang nâng để biết thay đổi tương ứng.

## 22. Checklist tích hợp Gradle plugin

- [ ] Ứng dụng có springdoc starter phù hợp với Spring MVC hoặc WebFlux.
- [ ] Spring Boot Gradle plugin và Java/Kotlin plugin được áp dụng.
- [ ] Phiên bản Gradle đáp ứng yêu cầu của plugin.
- [ ] Plugin ID và version được khai báo trong plugins block.
- [ ] apiDocsUrl trỏ tới endpoint đang được ứng dụng phục vụ.
- [ ] outputDir và outputFileName được xác định rõ.
- [ ] waitTimeInSeconds phù hợp với thời gian khởi động thực tế.
- [ ] customBootRun dùng đúng profile, environment và JVM options.
- [ ] groupedApiMappings chứa đúng URL của từng group nếu dùng nhiều tài liệu.
- [ ] requestHeaders không chứa token hard-code hoặc secret commit vào repository.
- [ ] trustStore được cấu hình nếu cần gọi HTTPS với CA riêng.
- [ ] generateOpenApiDocs chạy thành công trên máy local và CI.
- [ ] File JSON/YAML được parse và validate theo đúng OpenAPI version.
- [ ] Diff hợp đồng được review trước khi cập nhật baseline.
- [ ] Artifact được lưu và publish ở bước riêng theo release policy.
- [ ] Cấu hình 1.x cũ được loại bỏ sau khi nâng lên 2.x.

## 23. Tài liệu tham khảo chính thức

- [springdoc-openapi Gradle plugin](https://github.com/springdoc/springdoc-openapi-gradle-plugin): cách áp dụng plugin, task, openApi extension, grouped mappings, customBootRun và migration.
- [Gradle Plugin Portal](https://plugins.gradle.org/plugin/org.springdoc.openapi-gradle-plugin): plugin ID, version phát hành và cách khai báo plugin.
- [springdoc-openapi v2 documentation](https://springdoc.org/v2/): tích hợp springdoc với Spring Boot 3 và hướng dẫn Gradle plugin.
- [springdoc-openapi compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): quan hệ tương thích giữa Spring Boot và nhánh springdoc.
- [Gradle task configuration](https://docs.gradle.org/current/userguide/controlling_task_execution.html): dependsOn, finalizedBy và điều phối task.

## Kết luận

springdoc-openapi-gradle-plugin đưa việc xuất OpenAPI vào build thông qua task **generateOpenApiDocs**. Task khởi chạy Spring Boot application với cấu hình bootRun hoặc customBootRun, chờ endpoint tài liệu sẵn sàng, tải JSON/YAML và dừng ứng dụng. Có thể tùy chỉnh URL, thư mục đầu ra, thời gian chờ, profile, header, trust store và nhiều group. Tài liệu sinh ra phản ánh profile cùng runtime configuration được dùng ở lần chạy đó, vì vậy CI cần chuẩn hóa môi trường, validate document, review breaking change và lưu artifact. Với plugin 2.x, dùng task generateOpenApiDocs tích hợp sẵn; các task forked cũ thuộc nhánh 1.x không còn áp dụng.
