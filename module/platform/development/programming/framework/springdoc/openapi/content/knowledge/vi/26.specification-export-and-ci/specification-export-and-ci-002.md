# Phân biệt xuất hợp đồng với sinh mã phía gọi hoặc mã máy chủ

Springdoc-openapi và OpenAPI Generator đều làm việc với OpenAPI, nhưng giải quyết hai công việc khác nhau. **Springdoc xuất hợp đồng API từ ứng dụng Spring Boot đang chạy**; **OpenAPI Generator đọc hợp đồng để sinh mã client hoặc khung mã server**. Hiểu đúng chiều dữ liệu giúp đặt công cụ vào đúng giai đoạn build, tránh nhầm rằng có file OpenAPI nghĩa là đã có SDK hoặc server implementation.

Với module SPRINGDOC_OPENAPI, luồng thường gặp là:

1. Spring Boot controller, DTO, validation và annotation cung cấp thông tin về API.
2. Springdoc phân tích ứng dụng và tạo OpenAPI JSON/YAML.
3. CI lấy đặc tả thành artifact có version.
4. CI kiểm tra đặc tả rồi dùng OpenAPI Generator sinh client SDK hoặc server stub nếu dự án cần.

## 1. Phân biệt ba đầu ra

| Công việc | Đầu vào | Đầu ra | Công cụ tiêu biểu |
|---|---|---|---|
| Xuất hợp đồng | Controller, DTO, Spring configuration, validation và OpenAPI annotations trong ứng dụng | OpenAPI JSON/YAML | springdoc-openapi |
| Sinh mã client | File OpenAPI JSON/YAML đã được duyệt | SDK, API classes, model, serializer và HTTP client | OpenAPI Generator với generator loại CLIENT |
| Sinh mã server | File OpenAPI JSON/YAML đã được duyệt | Server project, API interface/controller stub, model và cấu hình khởi tạo | OpenAPI Generator với generator loại SERVER |

Ví dụ:

- Springdoc nhìn vào ProductController và xuất operation GET /api/products/{id} cùng schema ProductResponse.
- OpenAPI Generator đọc operation đó và sinh ProductApi cùng model ProductResponse trong Java client.
- Nếu chọn server generator spring, công cụ có thể sinh Spring Boot server skeleton với API contract tương ứng để nhóm phát triển bổ sung nghiệp vụ.

OpenAPI file là hợp đồng trung gian. Nó không phải source code client và cũng không phải implementation của server.

## 2. Hai hướng làm API phổ biến

### 2.1. Code-first: triển khai trước, xuất hợp đồng sau

Trong mô hình code-first, nhóm phát triển tạo controller, DTO, validation và annotation trong Spring Boot. Springdoc đọc các thành phần đó để sinh tài liệu:

~~~mermaid
flowchart TD
    A[Spring Controller + DTO + Validation] --> B[springdoc-openapi]
    B --> C[OpenAPI JSON / YAML]
    C --> D[Validate và Review]
    D --> E[Client SDK]
    D --> F[API documentation portal]
    D --> G[Contract artifact]
~~~

Luồng này phù hợp khi ứng dụng Spring Boot đã là nguồn triển khai chính. Hợp đồng được trích xuất từ code đang chạy hoặc từ môi trường build/test có cấu hình tương đương production.

### 2.2. API-first: duyệt hợp đồng trước, sinh khung mã sau

Trong mô hình API-first, nhóm phát triển viết và review OpenAPI trước khi triển khai:

~~~mermaid
flowchart TD
    A[OpenAPI contract] --> B[Validate và Review]
    B --> C[Generate server stubs]
    B --> D[Generate client SDK]
    C --> E[Implement business logic]
    E --> F[Spring Boot application]
    F --> G[springdoc hoặc contract verification]
~~~

Server stub tạo điểm bắt đầu để triển khai controller/interface theo hợp đồng. Client SDK có thể được phát hành cho frontend hoặc service khác trước khi server hoàn tất. Khi server chạy, cần xác minh API thực tế vẫn khớp hợp đồng đã duyệt.

Hai hướng có thể cùng tồn tại. Dù code-first hay API-first, nhóm cần xác định một nguồn hợp đồng chuẩn và quy trình xử lý khi code với OpenAPI lệch nhau.

## 3. Springdoc xuất OpenAPI ở runtime

Khi tích hợp springdoc vào Spring Boot, ứng dụng thường cung cấp các endpoint:

| Định dạng | URL mặc định | Công dụng |
|---|---|---|
| OpenAPI JSON | /v3/api-docs | Máy móc đọc, validate, so sánh và sinh mã. |
| OpenAPI YAML | /v3/api-docs.yaml | Artifact dễ review bằng Git và pull request. |
| Swagger UI | /swagger-ui.html | Người dùng xem operation, schema và thử request. |

Nếu cấu hình GroupedOpenApi, tài liệu từng group thường có URL dạng /v3/api-docs/{group}. Path có thể thay đổi theo springdoc.api-docs.path, context path hoặc cấu hình triển khai.

Ví dụ lấy tài liệu JSON và YAML từ ứng dụng đang chạy:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o build/openapi/catalog.json
curl -fsS http://localhost:8080/v3/api-docs.yaml -o build/openapi/catalog.yaml
~~~

Tùy chọn -f làm curl trả lỗi khi HTTP status không thành công; -sS giữ output gọn nhưng vẫn hiển thị lỗi. CI nên kiểm tra exit code và file đầu ra trước khi chuyển sang bước tiếp theo.

### 3.1. Xuất tài liệu trong CI

CI có thể khởi động ứng dụng với profile kiểm thử, chờ health check thành công rồi tải /v3/api-docs hoặc /v3/api-docs.yaml. Cần dùng cùng profile, feature flags và cấu hình có ảnh hưởng tới API như môi trường mà hợp đồng đại diện.

Một luồng đơn giản:

1. Build ứng dụng.
2. Khởi động ứng dụng trong integration-test environment.
3. Chờ endpoint readiness hoặc health check thành công.
4. Tải OpenAPI JSON/YAML.
5. Kiểm tra file không rỗng và có trường openapi, info, paths.
6. Validate và review thay đổi.
7. Lưu file như CI artifact.

Nếu CI không thể khởi động ứng dụng, có thể dùng một bước integration test hoặc pipeline chuyên biệt để tạo đặc tả. Không tự dựng một OpenAPI file bằng cách chép tay vài endpoint rồi xem đó là đầu ra của springdoc.

### 3.2. Xuất hợp đồng không đồng nghĩa sinh code

Sau khi tải /v3/api-docs, ta mới có tài liệu mô tả API. Muốn có Java client, TypeScript SDK hoặc server stub, cần gọi một code generator riêng với file đặc tả làm đầu vào.

Springdoc không tự tạo ApiClient, HTTP transport, model SDK hoặc server controller implementation chỉ vì nó xuất JSON/YAML. Swagger UI cũng chỉ trình bày và thử hợp đồng; nó không sinh SDK cho dự án.

## 4. OpenAPI Generator sinh mã từ hợp đồng

OpenAPI Generator nhận file OpenAPI và lựa chọn một generator phù hợp với đầu ra cần tạo. Hai lựa chọn Java thường gặp:

| Generator name | Loại | Đầu ra |
|---|---|---|
| java | CLIENT | Java client library, API classes, models và HTTP client theo library đã chọn. |
| spring | SERVER | Java Spring Boot server application/stubs, API và model. |

Không nên nhầm spring generator của OpenAPI Generator với thư viện springdoc-openapi. Generator spring tạo mã server từ hợp đồng; springdoc là thư viện chạy trong Spring Boot để xuất tài liệu OpenAPI.

Danh sách generator, mức ổn định và option thay đổi theo phiên bản. Kiểm tra generator trước khi đưa vào pipeline:

~~~bash
openapi-generator-cli list
openapi-generator-cli config-help -g java
openapi-generator-cli config-help -g spring
~~~

Lệnh list cho biết generator có sẵn; config-help cho biết option được hỗ trợ bởi đúng generator. Không sao chép option từ generator Java sang generator Spring nếu chưa xác minh.

### 4.1. Sinh Java client bằng CLI

Ví dụ tạo Java SDK từ catalog.yaml:

~~~bash
openapi-generator-cli generate \
  -i build/openapi/catalog.yaml \
  -g java \
  -o build/generated/catalog-client \
  --api-package com.example.catalog.client.api \
  --model-package com.example.catalog.client.model \
  --additional-properties=library=webclient,dateLibrary=java8,hideGenerationTimestamp=true
~~~

Trong ví dụ:

- -i chỉ file OpenAPI đầu vào.
- -g java chọn generator Java client.
- -o là thư mục mã được sinh.
- api-package và model-package tách API classes khỏi model.
- library=webclient chọn HTTP client library cho Java generator.
- hideGenerationTimestamp=true giúp giảm khác biệt không cần thiết giữa các lần sinh mã.

Các library và option có thể khác theo generator version. Dùng config-help -g java để xác nhận trước khi áp dụng.

Mã sinh ra là client SDK. Ứng dụng sử dụng SDK để gọi API qua HTTP; SDK không chứa implementation của API server.

### 4.2. Sinh server stub cho Spring

Ví dụ tạo Spring server skeleton:

~~~bash
openapi-generator-cli generate \
  -i build/openapi/catalog.yaml \
  -g spring \
  -o build/generated/catalog-server \
  --api-package com.example.catalog.server.api \
  --model-package com.example.catalog.server.model \
  --additional-properties=apiFirst=true
~~~

Generator spring là server generator. Option apiFirst cho biết tạo API từ đặc tả OpenAPI trong giai đoạn compile của server theo cơ chế generator hỗ trợ.

Server stub giúp tạo cấu trúc API và model nhất quán với hợp đồng. Nhóm phát triển vẫn cần triển khai service, repository, authorization, transaction, validation nghiệp vụ, persistence, observability và xử lý lỗi. Không coi mã scaffold là một server production hoàn chỉnh.

### 4.3. Chọn generator phù hợp

Trước khi sinh mã, kiểm tra:

- Generator có loại CLIENT hay SERVER đúng với mục đích không?
- Generator có trạng thái STABLE, BETA hay EXPERIMENTAL?
- HTTP client library, framework và phiên bản runtime có tương thích không?
- Các option về nullability, date/time, enum và discriminator có đáp ứng contract không?
- Generated code có license, dependency và security policy phù hợp không?
- OpenAPI version của input có được hỗ trợ đầy đủ không?

OpenAPI Generator hiện công bố hỗ trợ OpenAPI 3.1 ở trạng thái beta. Nếu contract dùng 3.1, cần kiểm tra riêng generator và schema đang sử dụng, chạy validate/generation trên đúng version đã pin, rồi review output. Không giả định mọi generator đều hỗ trợ mọi keyword 3.1 ở cùng mức độ.

## 5. Tích hợp OpenAPI Generator vào Maven

Nếu dự án dùng Maven, có thể đặt generation vào lifecycle generate-sources. Ví dụ dưới đây sinh Java client từ một contract đã được lưu trong repository:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.openapitools</groupId>
            <artifactId>openapi-generator-maven-plugin</artifactId>
            <version>7.27.0</version>
            <executions>
                <execution>
                    <id>generate-catalog-client</id>
                    <phase>generate-sources</phase>
                    <goals>
                        <goal>generate</goal>
                    </goals>
                    <configuration>
                        <inputSpec>src/main/openapi/catalog.yaml</inputSpec>
                        <generatorName>java</generatorName>
                        <output>target/generated-sources/openapi/catalog-client</output>
                        <apiPackage>com.example.catalog.client.api</apiPackage>
                        <modelPackage>com.example.catalog.client.model</modelPackage>
                        <configOptions>
                            <library>webclient</library>
                            <dateLibrary>java8</dateLibrary>
                            <hideGenerationTimestamp>true</hideGenerationTimestamp>
                        </configOptions>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Chạy:

~~~bash
./mvnw clean compile
~~~

Plugin chạy goal generate trong phase đã cấu hình. Mã được sinh vào target, là thư mục build có thể tạo lại. Kiểm tra README/plugin documentation của đúng phiên bản để biết cách đăng ký generated source root và các tùy chọn skip/cleanup phù hợp với cấu hình dự án.

### 5.1. Khi nào nên đặt generation ở generate-sources?

Đặt generation tại generate-sources khi mã được sinh là source input cần có trước compile. Các phase sau như compile và test sẽ dùng source đó.

Nếu chỉ xuất OpenAPI artifact từ ứng dụng đã chạy, không cần thêm OpenAPI Generator vào Maven lifecycle của service. Hai nhiệm vụ có thể nằm ở hai job riêng:

- Job documentation: khởi động ứng dụng và lưu OpenAPI JSON/YAML.
- Job SDK: nhận artifact OpenAPI đã duyệt và sinh client/server code.

Tách job giúp service không phải phụ thuộc code generator nếu nó không dùng mã được sinh.

## 6. Tích hợp OpenAPI Generator vào Gradle

Gradle plugin cung cấp task openApiGenerate và các extension để cấu hình generator. Ví dụ dùng Kotlin DSL:

~~~kotlin
plugins {
    id("org.openapi.generator") version "7.27.0"
}

tasks.register<org.openapitools.generator.gradle.plugin.tasks.GenerateTask>(
    "generateCatalogClient"
) {
    generatorName.set("java")
    inputSpec.set(file("src/main/openapi/catalog.yaml").absolutePath)
    outputDir.set(layout.buildDirectory.dir("generated-sources/openapi/catalog-client").get().asFile.absolutePath)
    apiPackage.set("com.example.catalog.client.api")
    modelPackage.set("com.example.catalog.client.model")
    configOptions.set(
        mapOf(
            "library" to "webclient",
            "dateLibrary" to "java8",
            "hideGenerationTimestamp" to "true"
        )
    )
}
~~~

Nếu generated source cần được compile trong cùng module, nối task generation với compile task và đăng ký output directory làm source set theo cách phù hợp với Gradle version của dự án. Tránh để task generation ghi đè source do developer tự viết.

Gradle plugin còn cung cấp task validate spec. Có thể dùng openApiValidate trước openApiGenerate hoặc đặt validation trong CI riêng để fail sớm khi contract sai.

## 7. Kiểm tra hợp đồng trước khi sinh mã

Không nên gọi code generator trên một file vừa tải về mà chưa kiểm tra. Tối thiểu cần xác minh:

- File không rỗng và parse được.
- Có openapi, info, paths phù hợp.
- Các reference được resolve và không có reference ngoài ý muốn.
- Request/response schema đúng với payload thực tế.
- Security schemes và requirement được mô tả đúng.
- Server URL và API version đúng môi trường phát hành.
- Các operation có operationId ổn định, không trùng.
- Các keyword/schema được generator hỗ trợ.

OpenAPI Generator có lệnh validate:

~~~bash
openapi-generator-cli validate \
  -i build/openapi/catalog.yaml \
  --recommend
~~~

Lệnh validate giúp phát hiện lỗi đặc tả và có thể đưa ra khuyến nghị. Nó không thay thế style lint, breaking-change detection, contract tests hoặc kiểm thử endpoint thật.

### 7.1. So sánh contract giữa các lần build

Khi OpenAPI artifact thay đổi, CI nên tạo diff so với phiên bản đã phát hành hoặc nhánh chính:

- Path hoặc HTTP method bị xóa.
- Required request field mới.
- Response schema thay đổi kiểu hoặc nullability.
- Status code hoặc security requirement bị đổi.
- Enum value bị xóa hoặc đổi tên.
- operationId, schema name hoặc reference bị đổi.
- Server URL hoặc API version bị đổi ngoài kế hoạch.

Không phải mọi thay đổi schema đều là breaking change trong mọi client, nhưng cần có quy tắc tương thích được nhóm thống nhất. Diff contract giúp reviewer thấy ảnh hưởng trước khi SDK mới được phát hành.

## 8. Quy trình CI/CD hoàn chỉnh

Một pipeline có thể chia thành các bước:

~~~mermaid
flowchart TD
    A[Build / Start test application] --> B[Export OpenAPI JSON/YAML]
    B --> C[Validate specification]
    C --> D[Lint + Contract diff]
    D --> E[Generate client SDK / server stubs]
    E --> F[Compile generated code]
    F --> G[Run contract and integration tests]
    G --> H[Publish versioned OpenAPI artifact]
    H --> I[Publish SDK package or server scaffold]
~~~

Gợi ý cách tổ chức:

1. **Export**: lấy đặc tả từ springdoc trong môi trường có cấu hình đã xác định.
2. **Validate**: chạy parser/validator và kiểm tra JSON/YAML.
3. **Lint**: áp dụng naming, tags, operationId, error response và security rules.
4. **Diff**: so sánh với artifact baseline để phát hiện thay đổi không tương thích.
5. **Generate**: chạy OpenAPI Generator với generator/version/options đã pin.
6. **Compile**: compile client SDK hoặc server stubs để phát hiện lỗi generated code.
7. **Test**: kiểm tra serialization, nullability, auth header và request/response mẫu.
8. **Publish**: lưu OpenAPI artifact và package SDK theo version đã duyệt.

Không bắt buộc mọi dự án phải sinh cả client lẫn server. Nếu chỉ cung cấp API cho frontend, job client SDK có thể là đủ. Nếu team viết server code-first bằng controller, có thể không cần server generator.

## 9. Giữ kết quả sinh mã ổn định và có thể tái tạo

Generated code phụ thuộc nhiều hơn file OpenAPI:

- Phiên bản OpenAPI Generator.
- Generator name và library.
- Generator options/config file.
- Template custom.
- Phiên bản JDK/Node hoặc runtime tương ứng.
- Input OpenAPI artifact.

Để build có thể tái tạo:

- Pin chính xác generator version trong Maven/Gradle hoặc CLI wrapper.
- Lưu config options cùng source control.
- Dùng cùng một OpenAPI artifact đã được review.
- Giảm timestamp động nếu generator hỗ trợ.
- Lưu generator version và checksum/hash của input trong build metadata.
- Chỉ thay đổi generator version qua pull request có diff output và test.

Không dùng tag latest hoặc dependency version động trong pipeline production. Một lần nâng generator có thể đổi tên model, kiểu dữ liệu, import, HTTP client hoặc cách serialize payload.

### 9.1. Generated code nên được quản lý thế nào?

Có hai cách thường gặp:

| Cách | Khi phù hợp | Điều cần lưu ý |
|---|---|---|
| Sinh trong mỗi build vào target/ hoặc build/ | Generated code là implementation detail của module và có thể tái tạo ổn định. | Không sửa tay file generated; compile phải phụ thuộc task generation. |
| Commit generated code hoặc publish thành package riêng | Consumer cần source/package ổn định hoặc không chạy generator trong build của họ. | Phải cập nhật code mỗi khi contract/generator thay đổi và kiểm tra diff. |

Nếu cần sửa cách sinh mã, dùng config option, template hoặc custom generator. Sửa trực tiếp file generated thường bị mất ở lần generation tiếp theo.

### 9.2. Custom template và ignore file

OpenAPI Generator hỗ trợ template tùy chỉnh. Có thể trích xuất template generator rồi thay đổi một số file Mustache, ví dụ thêm logging wrapper, license header hoặc quy ước package:

~~~bash
openapi-generator-cli author template \
  -g java \
  -o tools/openapi-templates/java
~~~

Sau đó dùng tùy chọn -t hoặc --template khi generate:

~~~bash
openapi-generator-cli generate \
  -i build/openapi/catalog.yaml \
  -g java \
  -t tools/openapi-templates/java \
  -o build/generated/catalog-client
~~~

File .openapi-generator-ignore có thể loại trừ một số file khỏi quá trình sinh lại. Dùng nó có chủ đích và review kết quả để tránh giữ lại file cũ không còn phù hợp với contract mới.

## 10. Phát hành hợp đồng và mã sinh ra

OpenAPI artifact và SDK package có vòng đời liên quan nhưng không đồng nhất:

- OpenAPI artifact ghi phiên bản API trong info.version và phiên bản đặc tả trong openapi.
- SDK package có version riêng theo chính sách package của team.
- OpenAPI Generator có version riêng của tool.
- Server application có version release riêng.

Ví dụ một release có thể gồm:

| Artifact | Version ví dụ |
|---|---|
| API contract info.version | 2.4.0 |
| OpenAPI Specification | 3.1.0 |
| Java SDK package | 2.4.0 hoặc version theo chính sách client |
| OpenAPI Generator | 7.27.0 |
| Spring Boot server | 4.1.x |

Không buộc các con số này phải giống nhau. Chúng biểu thị các vòng đời khác nhau. Gắn build metadata hoặc release tag để truy ngược SDK được sinh từ OpenAPI artifact và generator version nào.

## 11. Lưu ý khi dùng OpenAPI 3.1

OpenAPI Generator công bố hỗ trợ OpenAPI 3.1 ở trạng thái beta. Vì vậy:

- Kiểm tra release/version cụ thể thay vì suy luận từ việc CLI chấp nhận file.
- Thử với generator mục tiêu, không chỉ chạy validate tổng quát.
- Kiểm tra type union có null, oneOf/anyOf, discriminator và các JSON Schema keyword đang dùng.
- So sánh generated model và serializer với payload thật.
- Chạy contract tests cho field nullable, required và enum.
- Nếu một generator chưa xử lý đúng schema 3.1, đánh giá cách chuyển đổi có kiểm soát hoặc giữ contract 3.0 cho consumer đó; không chỉ sửa trường openapi bằng tay để ép parser.

Hỗ trợ ở mức parser không đồng nghĩa mọi generator và mọi feature đều có output hoàn chỉnh. Mỗi generator có feature set riêng.

## 12. Những lỗi thường gặp

- **Cho rằng springdoc sinh Java/TypeScript SDK**: springdoc chỉ xuất tài liệu; cần code generator riêng.
- **Cho rằng OpenAPI JSON là server code**: JSON/YAML chỉ là contract, không có business logic.
- **Dùng client generator để tạo server**: chọn generator type SERVER, ví dụ spring.
- **Dùng server generator để tạo SDK**: chọn generator type CLIENT, ví dụ java.
- **Không kiểm tra generator stability**: generator beta hoặc experimental có thể chưa phù hợp với pipeline release.
- **Sinh mã từ spec chưa validate**: lỗi reference, schema hoặc security có thể lan sang generated code.
- **Dùng option không được generator hỗ trợ**: xác minh bằng config-help -g name.
- **Sửa trực tiếp generated file**: thay đổi sẽ mất khi generate lại.
- **Không pin generator version**: build sau có thể sinh output khác dù contract không đổi.
- **Chỉ kiểm tra compile**: code compile được chưa chứng minh serialization và HTTP behavior khớp contract.
- **Chỉ publish SDK mà không publish spec**: khó review, diff và truy vết nguồn sinh.
- **Đồng nhất API version với generator version**: hai version có ý nghĩa độc lập.
- **Cho rằng hỗ trợ OpenAPI 3.1 đã hoàn chỉnh**: trạng thái hỗ trợ chung là beta; cần kiểm tra feature cụ thể.
- **Đưa spec/template không tin cậy vào generator**: review input trước khi chạy vì template hoặc dữ liệu đầu vào không tin cậy có thể tạo mã nguy hiểm.

## 13. Quy trình lựa chọn cho dự án Spring Boot

1. **Chọn nguồn hợp đồng**: controller Spring Boot với springdoc (code-first), hoặc OpenAPI file được duyệt (API-first).
2. **Xác định đầu ra cần có**: chỉ JSON/YAML, client SDK, server stub hay nhiều đầu ra.
3. **Chọn công cụ đúng vai trò**: springdoc để xuất contract; OpenAPI Generator để sinh mã.
4. **Chọn generator type**: CLIENT cho SDK, SERVER cho server skeleton.
5. **Kiểm tra compatibility**: OpenAPI version, generator stability, runtime và library.
6. **Pin phiên bản và config**: generator version, package names, templates và options.
7. **Đặt đúng build phase**: generation ở generate-sources khi source cần compile; export artifact ở job documentation khi không cần generated code trong module.
8. **Validate và diff contract**: phát hiện lỗi và breaking changes trước generation.
9. **Compile và test generated output**: xác minh kiểu dữ liệu, serialization và HTTP behavior.
10. **Publish có truy vết**: lưu OpenAPI artifact, SDK version, generator version và input checksum.

## 14. Checklist review

- [ ] Đã phân biệt export contract, client code generation và server stub generation.
- [ ] Đã xác định code-first hay API-first là nguồn hợp đồng chính.
- [ ] Springdoc chỉ được dùng để xuất tài liệu từ ứng dụng.
- [ ] OpenAPI Generator được chọn đúng generator type CLIENT/SERVER.
- [ ] Generator name và stability được xác minh.
- [ ] OpenAPI artifact được validate trước khi sinh mã.
- [ ] Generator version, config options và template được pin.
- [ ] Generated source nằm trong thư mục có thể tái tạo hoặc được quản lý như package riêng.
- [ ] Không sửa tay file generated.
- [ ] Compile và contract tests chạy trên output mới.
- [ ] OpenAPI artifact được version hóa và lưu cùng metadata truy vết.
- [ ] Đã kiểm tra compatibility của OpenAPI 3.1 nếu dùng schema 3.1.
- [ ] Input spec/template không tin cậy được review trước khi chạy generator.

## 15. Tài liệu tham khảo

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [springdoc-openapi v2 – Getting Started for Spring Boot 3](https://springdoc.org/v2/getting-started.html)
- [OpenAPI Generator – Usage](https://openapi-generator.tech/docs/usage/)
- [OpenAPI Generator – Maven and Gradle Plugins](https://openapi-generator.tech/docs/plugins/)
- [OpenAPI Generator – Generator List](https://openapi-generator.tech/docs/generators/)
- [OpenAPI Generator – Java Client Generator](https://openapi-generator.tech/docs/generators/java/)
- [OpenAPI Generator – Spring Server Generator](https://openapi-generator.tech/docs/generators/spring/)
- [OpenAPI Generator – Configuration Options](https://openapi-generator.tech/docs/configuration/)
- [OpenAPI Generator – Templates](https://openapi-generator.tech/docs/templating/)
- [OpenAPI Generator – Compatibility Matrix](https://github.com/OpenAPITools/openapi-generator#compatibility)

Springdoc xuất hợp đồng từ ứng dụng Spring Boot; OpenAPI Generator biến hợp đồng đó thành client SDK hoặc server skeleton. Hãy giữ rõ chiều dữ liệu, chọn đúng generator, validate trước khi sinh mã và pin cấu hình để build có thể tái tạo. Khi CI lưu cả OpenAPI artifact lẫn metadata của mã được sinh, nhóm có thể review contract, phát hành SDK và truy vết chính xác mỗi đầu ra được tạo từ phiên bản nào.
