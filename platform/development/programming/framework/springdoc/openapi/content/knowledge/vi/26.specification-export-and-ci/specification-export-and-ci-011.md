# Lưu hợp đồng cùng phiên bản phát hành và thông tin nguồn

## 1. Vì sao phải lưu OpenAPI cùng phiên bản phát hành?

Springdoc OpenAPI có thể tạo đặc tả trực tiếp từ ứng dụng đang chạy qua các endpoint như /v3/api-docs và /v3/api-docs.yaml. Cách này thuận tiện khi phát triển, nhưng một URL runtime không phải lúc nào cũng đủ để xác định chính xác hợp đồng đã được phát hành cùng một phiên bản ứng dụng.

Khi có sự cố, đội vận hành và đội tích hợp cần trả lời được:

- Đặc tả nào mô tả ứng dụng đang chạy?
- Đặc tả đó được tạo từ commit nào?
- API contract version là bao nhiêu?
- Artifact Spring Boot được build với phiên bản nào?
- Đặc tả đã được kiểm tra và phát hành qua pipeline nào?
- File JSON/YAML mà client đang dùng có đúng là file đã được kiểm duyệt không?

Nếu chỉ truy cập OpenAPI document mới nhất ở môi trường production, nội dung có thể đã thay đổi sau lần phát hành mà client đang tích hợp. Nếu chỉ lưu file trong repository mà không liên kết với artifact, khó xác định file đó có được tạo từ đúng source và cấu hình đã deploy hay không.

Vì vậy, OpenAPI document nên được quản lý như một artifact của release. Pipeline cần xuất document từ đúng build, kiểm tra nó, gắn thông tin phiên bản và source revision, sau đó lưu cùng release hoặc trong một artifact repository có thể truy vết.

## 2. Phân biệt các loại phiên bản

Có ba loại phiên bản thường xuất hiện cùng nhau nhưng mang ý nghĩa khác nhau:

| Loại phiên bản | Ví dụ | Ý nghĩa |
|---|---|---|
| OpenAPI Specification version | 3.1.0 | Phiên bản chuẩn mô tả cấu trúc document |
| API contract version | 1.4.0 | Phiên bản hợp đồng API dành cho client |
| Application version | 2.8.3 | Phiên bản artifact ứng dụng Spring Boot |

Ví dụ phần đầu của document:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: "1.4.0"
~~~

Trường openapi cho biết document tuân theo OpenAPI Specification 3.1.0. Trường info.version cho biết phiên bản API contract được mô tả.

Application version có thể là 2.8.3 trong khi API contract vẫn là 1.4.0. Một build mới có thể sửa lỗi nội bộ, cập nhật thư viện hoặc cải thiện hiệu năng mà không thay đổi hợp đồng HTTP.

Không tự động tăng info.version theo mỗi build number. Hãy cập nhật API contract version khi có quyết định phát hành hợp đồng mới theo chính sách versioning của tổ chức.

## 3. Gắn contract với source và artifact

Một bản OpenAPI phát hành nên có thể truy ngược tới:

- Tên service hoặc artifact.
- API contract version.
- Application version.
- OpenAPI Specification version.
- Git commit SHA.
- Build number hoặc pipeline run ID.
- Thời điểm tạo artifact nếu cần.
- Checksum của file OpenAPI.
- Phiên bản công cụ sinh và kiểm tra document.

Ví dụ manifest phát hành:

~~~yaml
service: catalog-api
apiContractVersion: 1.4.0
applicationVersion: 2.8.3
openApiSpecificationVersion: 3.1.0
sourceRevision: a1b2c3d4e5f6
buildRun: catalog-api-1842
openApiArtifact: catalog-api-openapi-1.4.0.yaml
sha256: 4a8f...example
~~~

Manifest này là metadata của release, không phải một phần bắt buộc của OpenAPI document. Có thể lưu nó cạnh file OpenAPI trong release bundle hoặc artifact repository.

Không cần công bố toàn bộ manifest cho người dùng API. Commit SHA, pipeline URL, branch name hoặc build host có thể là thông tin nội bộ. Hãy phân biệt metadata phục vụ truy vết nội bộ với metadata thực sự cần xuất hiện trong document public.

## 4. Xuất OpenAPI JSON và YAML từ Springdoc

Springdoc thường cung cấp hai endpoint:

~~~http
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

JSON phù hợp với công cụ tự động và xử lý bằng script. YAML thường dễ đọc khi review trong pull request hoặc lưu cùng tài liệu phát hành.

Nếu ứng dụng bật document groups, mỗi group có thể có endpoint riêng, ví dụ:

~~~http
GET /v3/api-docs/partner
GET /v3/api-docs/partner.yaml
~~~

Hãy xác định rõ release cần xuất document mặc định hay từng group. Nếu API public, partner và internal có hợp đồng khác nhau, mỗi document cần tên artifact và metadata riêng để tránh ghi đè hoặc phát hành nhầm audience.

Không nên tải document từ một môi trường tùy ý rồi gọi đó là contract của release. Hãy khởi chạy đúng artifact đang được kiểm tra với profile và cấu hình đã xác định, sau đó xuất document từ instance đó.

## 5. Chuẩn bị cấu hình cho lần export có thể tái lập

Để hai lần export từ cùng một source và cùng cấu hình tạo ra hợp đồng tương đương, pipeline cần cố định:

- Commit source được checkout.
- Phiên bản JDK và build tool.
- Dependency lock hoặc dependency version đã pin.
- Spring profile dùng khi sinh document.
- Environment variables ảnh hưởng tới API metadata.
- Feature flags ảnh hưởng tới controller, mapping hoặc schema.
- Các document group và filter.
- Phiên bản Springdoc và Swagger Core.
- Customizer và plugin tham gia quá trình export.

Không lấy server URL từ request header tùy ý trong pipeline. Dùng cấu hình contract profile với public base URL ổn định hoặc dùng một cấu hình canonical đã thống nhất.

Nếu metadata chứa build timestamp thay đổi ở mỗi lần chạy, file OpenAPI có thể khác dù contract không đổi. Chỉ đưa timestamp vào document nếu có yêu cầu vận hành rõ ràng; nếu không, lưu thời điểm build trong manifest riêng để giữ contract artifact ổn định hơn.

## 6. Cấu hình Maven để xuất document

Springdoc cung cấp Maven plugin riêng để tải OpenAPI document từ ứng dụng đang chạy. Plugin này không tự khởi động Spring Boot application; pipeline phải bảo đảm endpoint api-docs đã sẵn sàng trước khi goal generate chạy.

Ví dụ cấu hình plugin:

~~~xml
<plugin>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-maven-plugin</artifactId>
    <version>1.5</version>
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
        <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
        <outputFileName>openapi.json</outputFileName>
        <outputDir>target/openapi</outputDir>
    </configuration>
</plugin>
~~~

Phiên bản plugin trong ví dụ cần được pin và kiểm tra tương thích với Springdoc/Spring Boot của dự án. Không dùng version động trong pipeline phát hành.

Có thể kết hợp Spring Boot Maven Plugin để khởi động ứng dụng trước integration-test và dừng sau khi export:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>start-application</id>
            <phase>pre-integration-test</phase>
            <goals>
                <goal>start</goal>
            </goals>
        </execution>
        <execution>
            <id>stop-application</id>
            <phase>post-integration-test</phase>
            <goals>
                <goal>stop</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Maven lifecycle cần được cấu hình nhất quán với integration-test framework đang dùng. Nếu pipeline khởi động ứng dụng bằng container hoặc service riêng, không cần thêm cơ chế start/stop này; chỉ cần bảo đảm endpoint sẵn sàng trước bước export. Nếu cần cả build-info và start/stop, hãy gộp các execution vào một khai báo Spring Boot Maven Plugin trong POM.

## 7. Xuất document bằng curl hoặc PowerShell

Có thể tải document trực tiếp khi ứng dụng đã chạy:

~~~bash
mkdir -p target/openapi

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output target/openapi/openapi.json

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output target/openapi/openapi.yaml
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path target/openapi | Out-Null
Invoke-WebRequest -Uri http://localhost:8080/v3/api-docs -OutFile target/openapi/openapi.json
Invoke-WebRequest -Uri http://localhost:8080/v3/api-docs.yaml -OutFile target/openapi/openapi.yaml
~~~

Dùng fail-fast để pipeline dừng khi endpoint trả lỗi. Sau khi tải, kiểm tra file không rỗng và response thực sự là OpenAPI JSON/YAML. Một trang đăng nhập HTML trả về status 200 không phải là document hợp lệ.

Nếu API docs được bảo vệ bằng authentication, pipeline cần credential riêng có quyền đọc tài liệu. Không ghi token hoặc password vào command log; dùng secret store của CI.

## 8. Xuất từ đúng artifact được phát hành

Một lỗi phổ biến là export document từ source tree hiện tại, sau đó phát hành một JAR được build ở bước khác hoặc từ commit khác. Khi đó, OpenAPI artifact và application artifact không còn cùng provenance.

Quy trình nên gắn chúng trong một chuỗi:

~~~text
Git commit
    |
    v
Build application artifact
    |
    v
Run tests and start that artifact
    |
    v
Export OpenAPI JSON/YAML
    |
    v
Validate and compare contract
    |
    v
Create release manifest and checksums
    |
    v
Publish application + OpenAPI artifacts
~~~

Nếu build lại ứng dụng sau khi export, cần xác minh build mới vẫn dùng cùng source revision, dependencies và cấu hình. Tốt nhất là export từ chính JAR/container image đã vượt qua các bước kiểm thử sẽ được phát hành.

Không dùng document được tạo từ local developer environment để thay thế artifact của release. Máy local có thể có profile, environment variable, dependency cache hoặc feature flag khác pipeline.

## 9. Gắn API contract version với application build

Application version thường được quản lý trong Maven POM hoặc Gradle project version. API contract version nên được quản lý riêng, ví dụ bằng property:

~~~yaml
app:
  api:
    contract-version: "1.4.0"
~~~

Springdoc có thể sử dụng giá trị này khi tạo Info Object:

~~~java
@ConfigurationProperties(prefix = "app.api")
public record ApiContractProperties(
    String contractVersion
) {
}
~~~

~~~java
@Bean
OpenAPI catalogOpenAPI(ApiContractProperties properties) {
    return new OpenAPI()
        .info(new Info()
            .title("Catalog API")
            .version(properties.contractVersion()));
}
~~~

Trong release pipeline, đặt contract version từ release configuration đã được phê duyệt. Không tự suy ra contract version bằng cách lấy application version nếu hai chính sách versioning độc lập.

Nếu một build chứa nhiều document group, có thể mỗi group có API contract version riêng. Khi đó cần đặt tên artifact theo service và group để tránh nhầm lẫn.

## 10. Thêm build version bằng Spring Boot BuildProperties

Spring Boot có thể tạo build metadata trong artifact để ứng dụng đọc lại version đã đóng gói.

Với Maven, cấu hình goal build-info của Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>build-info</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Với Gradle:

~~~groovy
springBoot {
    buildInfo()
}
~~~

Khi artifact chứa META-INF/build-info.properties, Spring Boot có thể cung cấp bean BuildProperties với thông tin như artifact, group, name, version và time.

Bean này có thể không tồn tại nếu build-info chưa được tạo. Nếu ứng dụng có profile test hoặc local không tạo build metadata, dùng ObjectProvider hoặc cấu hình có điều kiện thay vì bắt buộc inject BuildProperties ở mọi môi trường.

BuildProperties giúp document hoặc manifest phản ánh version của artifact thực sự đang chạy, thay vì một giá trị được nhập lại thủ công.

## 11. Gắn source revision bằng Git metadata

Để truy vết source, pipeline nên lưu Git commit SHA đầy đủ hoặc short SHA. Spring Boot có thể đọc file git.properties thông qua GitProperties nếu build được cấu hình tạo file đó.

Ví dụ lấy revision trong code:

~~~java
GitProperties git = gitPropertiesProvider.getIfAvailable();

if (git != null && StringUtils.hasText(git.getShortCommitId())) {
    openApi.addExtension(
        "x-source-revision",
        git.getShortCommitId()
    );
}
~~~

Bean method cần nhận ObjectProvider<GitProperties> gitPropertiesProvider. File git.properties có thể được tạo bằng plugin Git metadata phù hợp với Maven hoặc Gradle.

Không giả định GitProperties luôn tồn tại. Source archive, shallow clone hoặc pipeline không checkout thư mục .git có thể khiến plugin không tạo metadata như mong đợi.

Commit SHA là thông tin truy vết hữu ích. Branch name, repository URL, build agent hostname và thông tin pipeline nội bộ không nhất thiết phải công bố trong OpenAPI public.

## 12. Thêm build metadata vào OpenAPI có kiểm soát

Có thể thêm vendor extensions vào OpenAPI model:

~~~java
@Bean
OpenApiCustomizer releaseMetadataCustomizer(
        ObjectProvider<BuildProperties> buildProvider,
        ObjectProvider<GitProperties> gitProvider) {

    return openApi -> {
        BuildProperties build = buildProvider.getIfAvailable();
        GitProperties git = gitProvider.getIfAvailable();

        if (build != null && StringUtils.hasText(build.getVersion())) {
            openApi.addExtension(
                "x-application-version",
                build.getVersion()
            );
        }

        if (git != null && StringUtils.hasText(git.getShortCommitId())) {
            openApi.addExtension(
                "x-source-revision",
                git.getShortCommitId()
            );
        }
    };
}
~~~

Các extension bắt đầu bằng x- là metadata riêng, không phải trường chuẩn mà mọi client generator bắt buộc phải hiểu.

Nếu document được phân phối ra bên ngoài, hãy cân nhắc chỉ công bố application version. Source revision có thể được giữ trong release manifest nội bộ. Không thêm branch, commit message hoặc URL repository private nếu không có lý do.

Không đưa secret, access token, connection string, hostname database hoặc cấu hình nội bộ vào extension. OpenAPI document có thể được tải xuống và lưu lâu dài ở phía client.

## 13. Đặt tên và tổ chức OpenAPI artifact

Tên artifact cần cho biết service, group và API contract version. Ví dụ:

~~~text
release/
  catalog-api/
    1.4.0/
      openapi.json
      openapi.yaml
      manifest.yaml
      SHA256SUMS
~~~

Nếu có nhiều group:

~~~text
release/
  catalog-api/
    1.4.0/
      public-openapi.yaml
      partner-openapi.yaml
      internal-openapi.yaml
      manifest.yaml
~~~

Không ghi đè file của một version đã phát hành. Nếu contract version 1.4.0 đã được publish, một document mới khác nội dung không nên âm thầm thay thế cùng đường dẫn. Hãy tạo version mới hoặc dùng quy trình sửa release có audit và chính sách rõ ràng.

Artifact có thể được lưu trong:

- Maven repository hoặc package registry.
- Generic artifact repository.
- Object storage có versioning.
- Release assets gắn với Git tag.
- Developer portal hoặc API catalog.
- OCI artifact registry nếu nền tảng hỗ trợ phân phối tài liệu theo dạng OCI.

Chọn một nguồn chuẩn (source of truth) và ghi rõ quyền sở hữu, retention, access policy.

## 14. Tạo checksum để xác minh file

Checksum giúp xác minh file được tải xuống có giống artifact đã phát hành hay không.

Trên Linux/macOS:

~~~bash
sha256sum openapi.json openapi.yaml > SHA256SUMS
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash target/openapi/openapi.json -Algorithm SHA256
Get-FileHash target/openapi/openapi.yaml -Algorithm SHA256
~~~

Lưu checksum trong release manifest hoặc file SHA256SUMS cạnh artifact. Khi consumer tải document, họ có thể kiểm tra hash trước khi sử dụng.

Checksum chỉ chứng minh nội dung file khớp với hash đã biết. Nếu cần xác minh nguồn phát hành, hãy ký manifest hoặc artifact bằng cơ chế signing của tổ chức và bảo vệ signing key trong CI secret store hoặc hệ thống KMS.

Không lưu private signing key trong repository hoặc trong OpenAPI document.

## 15. Kiểm tra document trước khi phát hành

Pipeline cần xác minh ít nhất các lớp sau:

| Lớp kiểm tra | Nội dung |
|---|---|
| File | File tồn tại, không rỗng, encoding đúng |
| Cấu trúc | JSON/YAML parse được |
| OpenAPI | Document tuân theo đúng phiên bản specification |
| References | Các local/external $ref được resolve |
| Schema | Schema hợp lệ và có type/constraint phù hợp |
| Operation | Path, method, operationId và response đầy đủ |
| Security | Scheme và requirement đúng với API runtime |
| Environment | Server URL không trỏ tới hostname sai hoặc nội bộ |
| Policy | Không lộ secret hoặc dữ liệu không được công bố |
| Compatibility | Không có breaking change ngoài dự kiến |

Một file parse được chưa chắc là OpenAPI hợp lệ. Một document hợp lệ theo chuẩn cũng chưa chắc tuân thủ quy ước nội bộ như operationId naming, error response, pagination hoặc security policy.

Nên dùng validator và linter riêng. Pin version công cụ trong CI để cùng một commit không nhận kết quả khác nhau chỉ vì công cụ tự cập nhật.

## 16. Validate bằng OpenAPI Generator CLI

OpenAPI Generator CLI có lệnh validate để kiểm tra document:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.yaml
~~~

Lệnh này hữu ích để phát hiện cấu trúc OpenAPI không hợp lệ hoặc lỗi mà parser của generator nhận diện được. Tuy nhiên, kết quả phụ thuộc phiên bản CLI và khả năng hỗ trợ OpenAPI version/features.

Nếu dùng OpenAPI 3.1, hãy chọn phiên bản validator và generator có hỗ trợ 3.1. Không hạ document xuống 3.0 chỉ để làm công cụ cũ chạy được mà không đánh giá mất mát ngữ nghĩa.

Ngoài validate, có thể tạo client/server stub trong một job riêng để phát hiện vấn đề tương thích sớm. Việc code generation thành công không thay thế contract lint hoặc breaking-change diff.

## 17. Lint theo quy ước tổ chức

Spectral là một lựa chọn để kiểm tra style và governance rules của OpenAPI. Ví dụ:

~~~bash
spectral lint target/openapi/openapi.yaml
~~~

Rule set có thể yêu cầu:

- Mọi operation có summary và operationId.
- Error response dùng schema chuẩn.
- Mọi API cần bảo mật có security requirement.
- Không dùng server URL nội bộ trong document public.
- Query parameter pagination có mô tả.
- Schema có description hoặc example theo quy ước.
- Tag và operationId tuân theo naming convention.

Rule set cần được version hóa cùng pipeline. Nếu thay đổi rule, nên review như một thay đổi CI policy để tránh đột ngột làm fail các API cũ mà không có lộ trình.

Không nên đặt rule quá nghiêm đến mức buộc nhóm phát triển thêm metadata vô nghĩa. Mục tiêu là tạo hợp đồng nhất quán và hữu ích cho client.

## 18. Phát hiện breaking change so với release trước

Một document mới có thể hợp lệ nhưng vẫn phá vỡ client hiện hữu. Ví dụ:

- Xóa path hoặc HTTP method.
- Xóa response property đang được client dùng.
- Đổi kiểu dữ liệu của property.
- Đổi parameter từ optional thành required.
- Thêm enum value trong hệ thống client xử lý enum đóng.
- Thay đổi security requirement khiến client cần credential mới.
- Đổi response status hoặc media type.
- Thu hẹp range hoặc constraint của request.

Có thể dùng oasdiff để so sánh document cũ và mới:

~~~bash
oasdiff breaking previous/openapi.yaml candidate/openapi.yaml
~~~

Lệnh breaking tập trung phát hiện các thay đổi có nguy cơ ảnh hưởng client. Hãy pin version oasdiff và xác định exit code/policy mà pipeline dùng.

Không phải mọi thay đổi đều breaking với mọi client. Ví dụ thêm optional response field thường tương thích với client bỏ qua field lạ, nhưng có thể ảnh hưởng client dùng strict deserialization. Cần kết hợp công cụ diff với chính sách compatibility của hệ thống.

Nếu pipeline phát hiện breaking change, yêu cầu review hoặc approval theo quy trình release thay vì tự động bỏ qua cảnh báo.

## 19. So sánh đúng hai hợp đồng

Khi so sánh contract, hai file phải đại diện cho hai phiên bản API có thể so sánh:

- Baseline là document của release gần nhất đã công bố cho cùng API audience.
- Candidate là document được sinh từ commit đang kiểm tra.
- Cùng document group phải được so với nhau.
- Cùng cách chuẩn hóa server URL và environment metadata.
- Cùng phiên bản validator/diff tool hoặc có kế hoạch nâng cấp công cụ.

Không so public API với internal API hoặc document của group khác. Không so file staging có server URL riêng với file production nếu khác biệt duy nhất là môi trường nhưng pipeline chưa chuẩn hóa metadata.

Có thể loại bỏ hoặc chuẩn hóa trường deployment-specific trước khi diff nếu chính sách cho phép. Việc chuẩn hóa phải giữ nguyên path, operation, schema, security và các phần thuộc hợp đồng thực sự.

Lưu baseline theo release artifact thay vì dùng một file OpenAPI mới nhất không rõ nguồn.

## 20. Pipeline CI mẫu

Một pipeline export và kiểm tra OpenAPI có thể gồm các bước:

~~~bash
set -euo pipefail

# 1. Build and test the exact source revision
./mvnw -B clean verify

# 2. Ensure the application is running with the contract profile
# The application must use the artifact built by this pipeline.

# 3. Export the document
mkdir -p target/openapi
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output target/openapi/openapi.yaml

# 4. Validate and lint
openapi-generator-cli validate -i target/openapi/openapi.yaml
spectral lint target/openapi/openapi.yaml

# 5. Compare with the previous published contract
oasdiff breaking previous/openapi.yaml target/openapi/openapi.yaml

# 6. Create a checksum
sha256sum target/openapi/openapi.yaml \
  > target/openapi/SHA256SUMS
~~~

Đây là skeleton pipeline. Phần khởi động ứng dụng, readiness check, lấy baseline, xử lý exit code và publish artifact cần được nối với CI platform của tổ chức.

Nếu dùng Maven Springdoc plugin để export, thay bước curl bằng goal generate đã cấu hình. Dù dùng cách nào, phải bảo đảm ứng dụng đang chạy là artifact vừa build và dùng profile contract đã xác định.

Không để pipeline tiếp tục publish khi validate hoặc breaking-change check thất bại, trừ khi có approval rõ ràng và release record ghi nhận ngoại lệ.

## 21. Gắn metadata nguồn vào release manifest

Manifest có thể được tạo sau khi export:

~~~yaml
service: catalog-api
apiContractVersion: "1.4.0"
applicationVersion: "2.8.3"
openApiSpecificationVersion: "3.1.0"
source:
  repository: catalog-api
  revision: a1b2c3d4e5f6
build:
  runId: "1842"
  profile: contract
artifacts:
  - name: openapi.yaml
    sha256: 4a8f...example
  - name: catalog-api.jar
    sha256: 9b2d...example
~~~

Manifest liên kết OpenAPI document với JAR hoặc container image đã được kiểm thử. Nếu có nhiều group, liệt kê từng file cùng group name và checksum.

Không nhất thiết phải nhúng toàn bộ metadata này vào OpenAPI document. Manifest riêng cho phép giữ document public gọn hơn trong khi release system vẫn có đầy đủ provenance.

Hãy giữ manifest cùng artifact và bảo đảm các đường dẫn artifact là bất biến.

## 22. Bảo vệ thông tin khi export và publish

OpenAPI document có thể tiết lộ:

- Internal hostname và network path.
- Endpoint quản trị hoặc operation chưa dành cho public.
- Tên hệ thống phụ thuộc.
- Schema chứa dữ liệu nội bộ.
- Ví dụ request/response chứa dữ liệu thật.
- Security scheme hoặc OAuth URL của môi trường không phù hợp.
- Source revision, branch hoặc build metadata nội bộ.

Trước khi publish:

1. Chọn đúng document group dành cho audience.
2. Kiểm tra server URL và path.
3. Dùng dữ liệu giả trong example.
4. Không đưa secret/token thật vào description hoặc example.
5. Kiểm tra security scheme không chứa credential.
6. Không công bố internal host, database endpoint hoặc actuator route.
7. Quản lý quyền đọc artifact repository.
8. Scan document bằng policy hoặc secret scanner nếu cần.

Bảo vệ endpoint /v3/api-docs trong runtime và kiểm soát quyền truy cập artifact đã phát hành là hai lớp riêng. Tắt Swagger UI không đồng nghĩa file OpenAPI đã publish được bảo vệ.

## 23. Phát hành artifact bất biến và hỗ trợ rollback

Sau khi validate và approval, publish OpenAPI document cùng release:

- Dùng path có API contract version.
- Lưu manifest và checksum.
- Gắn artifact với source revision và application artifact.
- Giữ lại release cũ theo retention policy.
- Không ghi đè contract đã phát hành.
- Có thể tải lại chính xác document của một release bất kỳ.

Khi rollback ứng dụng, đội vận hành cần biết document nào đi cùng application artifact được rollback. Không nên lấy document từ nhánh main mới nhất nếu ứng dụng đang chạy một release cũ.

Nếu API contract version không đổi giữa hai build, có thể lưu nhiều build provenance dưới cùng một contract version trong release history, nhưng cần quy tắc rõ ràng để tránh ghi đè file canonical. Ví dụ dùng build-specific subfolder trong manifest hoặc artifact metadata.

## 24. Các lỗi thường gặp khi lưu và phát hành hợp đồng

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| OpenAPI artifact không khớp JAR đã deploy | Export từ source/build khác với artifact phát hành |
| info.version thay đổi mỗi lần build | Dùng application version thay API contract version |
| Thiếu source revision | Build không tạo git.properties hoặc manifest không lưu commit |
| File JSON/YAML rỗng | Endpoint chưa sẵn sàng, authentication hoặc export lỗi |
| File có HTML thay vì OpenAPI | Redirect tới login page hoặc proxy error page |
| Staging URL lọt vào public document | Dùng sai profile hoặc server URL từ môi trường |
| Group document bị ghi đè | Tất cả group dùng chung output filename |
| Diff luôn báo khác | Timestamp, server URL hoặc metadata động chưa được chuẩn hóa |
| Breaking change không bị phát hiện | So sai baseline, sai group hoặc công cụ thiếu hỗ trợ |
| Validator local và CI khác nhau | Version tool hoặc dependency không được pin |
| Artifact cũ bị thay nội dung | Publish ghi đè đường dẫn version đã tồn tại |
| Checksum không khớp | File bị thay đổi sau bước hash hoặc publish |
| Source metadata làm lộ nội bộ | Công bố branch, repository URL hoặc commit không cần thiết |

Khi điều tra, đối chiếu source SHA, application artifact checksum, OpenAPI checksum và pipeline run ID. Chỉ nhìn tên file hoặc info.version không đủ để chứng minh hai artifact được tạo từ cùng một release.

## 25. Checklist trước khi phát hành OpenAPI

Trước khi publish contract artifact:

1. Build ứng dụng từ commit đã xác định.
2. Chạy test và khởi động chính artifact vừa build.
3. Kích hoạt profile contract với cấu hình server ổn định.
4. Export đúng JSON/YAML và từng document group cần phát hành.
5. Xác minh file không rỗng và parse được.
6. Validate theo OpenAPI Specification version đã khai báo.
7. Lint theo governance rules.
8. Resolve các $ref và kiểm tra component schema.
9. So sánh với baseline cùng API audience để phát hiện breaking change.
10. Xác minh API contract version độc lập với application version.
11. Ghi source revision và build run vào manifest.
12. Tạo checksum và ký artifact nếu quy trình yêu cầu.
13. Scan thông tin nhạy cảm và server URL.
14. Publish artifact theo đường dẫn version bất biến.
15. Lưu baseline và release metadata để hỗ trợ rollback.

OpenAPI document là hợp đồng có vòng đời riêng và cần được gắn với bản phát hành tạo ra nó. Khi pipeline xuất tài liệu từ đúng application artifact, kiểm tra tính hợp lệ và tương thích, lưu source revision cùng checksum rồi publish bất biến, đội phát triển có thể xác định chính xác client đang dùng hợp đồng nào và khôi phục tài liệu tương ứng với bất kỳ release nào.

