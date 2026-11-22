# Theo dõi nguồn gốc, quyền sở hữu và phiên bản của tài liệu công bố

Một tệp OpenAPI được tạo ra từ ứng dụng Spring Boot có thể được dùng trong nhiều nơi: Swagger UI, cổng developer portal, SDK generator, contract test, kho artifact hoặc hệ thống tích hợp của đối tác. Khi một consumer nhận được tệp JSON/YAML, họ cần biết **tài liệu thuộc API nào, ai chịu trách nhiệm, được sinh từ source revision nào, bằng môi trường nào và tương ứng với bản phát hành nào**.

springdoc-openapi chịu trách nhiệm tạo OpenAPI document từ các endpoint và metadata trong ứng dụng. Việc theo dõi nguồn gốc và phân phối tài liệu cần thêm quy trình build/release: lưu source commit, phiên bản công cụ, group được export, checksum, thông tin owner và địa chỉ artifact đã công bố. Những dữ liệu này tạo thành provenance của tài liệu.

## 1. Phân biệt tài liệu OpenAPI, API và artifact phát hành

Một số giá trị version thường xuất hiện cạnh nhau nhưng có ý nghĩa khác nhau:

| Giá trị | Nằm ở đâu | Ý nghĩa |
| --- | --- | --- |
| OpenAPI Specification version | Field gốc `openapi`, ví dụ `3.1.0` | Phiên bản cú pháp/đặc tả mà document tuân theo |
| OpenAPI document version | `info.version` | Phiên bản của chính OpenAPI document |
| API runtime version | Quy ước API của hệ thống, ví dụ `/api/v1` hoặc header version | Phiên bản hành vi API mà server cung cấp |
| springdoc-openapi version | Dependency của ứng dụng | Phiên bản thư viện tạo tài liệu |
| Artifact release version | Tên package, tag hoặc đường dẫn publish | Phiên bản bất biến của tệp tài liệu đã phát hành |
| Source revision | Git commit SHA | Revision source cụ thể dùng để tạo tài liệu |
| Build run ID | CI pipeline | Lần chạy đã tạo ra artifact |

Không gộp các giá trị này thành một chuỗi. Ví dụ document có thể khai báo `openapi: 3.1.0`, `info.version: 1.4.2`, mô tả API runtime `/api/v1`, được sinh bằng springdoc-openapi `2.x`, từ Git commit `8f2a...`, rồi publish artifact `shop-openapi-public:1.4.2`.

OpenAPI Specification quy định `info.version` là version của OpenAPI document và phân biệt nó với version của OpenAPI Specification cũng như version của API implementation. Một tổ chức có thể chọn đồng bộ `info.version` với API release để dễ vận hành, nhưng phải ghi rõ đây là quy ước của dự án. Nếu document version và API version khác nhau, lưu cả hai trong release manifest.

## 2. Xác định nguồn gốc của tài liệu

Provenance trả lời câu hỏi: tệp được tạo ra từ đâu, khi nào và bằng quy trình nào? Với OpenAPI được sinh từ Spring Boot, tối thiểu cần liên kết được các dữ liệu sau:

- Repository và source revision chính xác.
- Release tag hoặc branch dùng để tạo tài liệu.
- Trạng thái working tree tại thời điểm build.
- CI workflow, build run ID và build platform.
- JDK, Spring Boot, springdoc-openapi và build plugin version.
- Profile Spring, group OpenAPI và cấu hình có ảnh hưởng đến document.
- Đường dẫn, định dạng, kích thước và SHA-256 digest của tệp.
- Artifact version, nơi publish và thời điểm công bố.

Chỉ lưu branch name như `main` là chưa đủ. Branch có thể di chuyển theo thời gian. Commit SHA mới là định danh bất biến để xác định chính xác source revision. Tương tự, chỉ ghi `springdoc-openapi 2.x` chưa đủ khi cần tái tạo kết quả; hãy lưu version cụ thể đã resolve trong dependency lockfile hoặc dependency report.

Một bản build release nên chạy từ commit đã được review và gắn tag. Nếu build từ working tree có thay đổi chưa commit, ghi rõ trạng thái đó và tránh công bố như một release chính thức.

## 3. Phân biệt source provenance và build provenance

Hai loại provenance bổ sung cho nhau:

| Loại | Trả lời câu hỏi | Bằng chứng thường dùng |
| --- | --- | --- |
| Source provenance | Source revision được tạo và review theo quy trình nào? | Git commit, pull request, reviewer, branch protection, signed commit/tag |
| Build provenance | Artifact được tạo từ source nào, bởi hệ thống nào và bằng quy trình nào? | CI run, build definition, tool versions, dependency inputs, artifact digest, attestation |

Ví dụ, Git commit có thể đã được review và merge đúng quy trình, nhưng artifact publish lại được tạo từ một commit khác hoặc từ build máy cá nhân. Source provenance tốt không tự chứng minh artifact đang phân phối được tạo từ source đó. Build provenance liên kết artifact cụ thể với source revision và build process thực tế.

SLSA mô tả build provenance như thông tin có thể kiểm chứng về cách artifact được tạo ra. Mô hình này liên kết output artifact với build definition, dependencies và build platform. Với tài liệu OpenAPI, có thể áp dụng cùng nguyên tắc cho file JSON/YAML và sidecar manifest của nó.

## 4. Đặt quyền sở hữu tài liệu rõ ràng

Mỗi tài liệu được công bố cần có một nhóm chịu trách nhiệm nội dung và một nhóm chịu trách nhiệm phân phối. Hai vai trò có thể thuộc cùng một team, nhưng cần xác định rõ:

| Vai trò | Trách nhiệm |
| --- | --- |
| API owner | Xác nhận endpoint, schema, security và semantics được mô tả đúng |
| Documentation owner | Duy trì mô tả, contact, examples và lịch sử thay đổi |
| Build/release owner | Duy trì pipeline export, validation, checksum và publication |
| Consumer/integration owner | Xác nhận khả năng tương thích và thông báo vấn đề từ phía sử dụng |

Không nên chỉ ghi tên cá nhân tạo file. Người tạo có thể chuyển nhóm hoặc rời dự án, trong khi trách nhiệm API vẫn tồn tại. Dùng tên team hoặc service owner làm đầu mối chính; có thể bổ sung contact cá nhân trong quy trình review.

Đối với repository Git, có thể đặt quy tắc review cho source controller, cấu hình OpenAPI, pipeline và thư mục tài liệu bằng CODEOWNERS hoặc cơ chế tương đương. Pull request thay đổi contract cần có API owner review; thay đổi publication workflow cần có release/platform owner review.

Quyền sở hữu cũng cần có quy trình chuyển giao. Khi API chuyển team, cập nhật contact, reviewer rule, runbook và quyền truy cập artifact repository. Đừng để tài liệu vẫn trỏ đến email hoặc URL hỗ trợ đã ngừng hoạt động.

## 5. Ghi metadata owner trong OpenAPI document

OpenAPI Info Object có các trường metadata tiêu chuẩn như `title`, `description`, `contact`, `license` và `version`. Dùng `contact` để chỉ đầu mối hỗ trợ API và `externalDocs` để liên kết đến hướng dẫn đầy đủ.

Ví dụ cấu hình OpenAPI bean trong Spring Boot:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiMetadataConfiguration {

    @Bean
    OpenAPI shopOpenApi(
            @Value("${api.document.version}") String documentVersion) {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .description("API quản lý đơn hàng và khách hàng")
                .version(documentVersion)
                .contact(new Contact()
                    .name("Shop API Team")
                    .email("api-team@example.org")
                    .url("https://docs.example.org/shop/support")));
    }
}
~~~

Các giá trị `example.org` là placeholder cần thay bằng contact và URL thực tế của tổ chức. Không đưa thông tin cá nhân hoặc địa chỉ nội bộ nhạy cảm vào document public.

Có thể dùng `@OpenAPIDefinition` và `@Info` để khai báo metadata bằng annotation. Với version lấy từ cấu hình build/environment, `OpenAPI` bean thường thuận tiện hơn vì có thể inject property. Dù dùng cách nào, hãy bảo đảm version và contact không bị thay đổi tùy môi trường một cách ngoài ý muốn.

`contact` là thông tin hỗ trợ API. Nó không tự xác định ai đã review release hoặc ai đã chạy build. Reviewer và build actor cần được lưu trong hệ thống quản lý source/CI hoặc provenance manifest.

## 6. Dùng extension cho metadata riêng của tổ chức

OpenAPI cho phép Specification Extensions với tên bắt đầu bằng `x-`. Có thể bổ sung team owner, mã service hoặc link runbook nếu công cụ tiêu thụ biết cách xử lý:

~~~yaml
info:
  title: Shop API
  version: 1.4.2
  contact:
    name: Shop API Team
    email: api-team@example.org
  x-owner-team: commerce-platform
  x-support-url: https://docs.example.org/shop/support
~~~

Các extension như `x-owner-team` là metadata riêng của tổ chức, không phải field tiêu chuẩn bắt buộc của OpenAPI. Công cụ không hiểu extension có thể bỏ qua chúng. Vì vậy:

- Giữ metadata hỗ trợ phổ biến trong `info.contact`.
- Dùng extension cho thông tin bổ sung có giá trị trong tooling nội bộ.
- Không đặt token, password, private key hoặc secret trong extension.
- Không dùng extension thay cho access control hoặc chữ ký provenance.
- Không giả định `x-owner-team` chứng minh team đó đã phê duyệt artifact.

Thông tin thay đổi theo từng lần build như commit SHA, build run ID, timestamp và digest thường phù hợp hơn với sidecar manifest/attestation. Cách này giúp document tập trung mô tả API và giúp pipeline ghi provenance sau khi file đã được sinh.

## 7. Tạo release manifest bên cạnh OpenAPI file

Một manifest riêng có thể liên kết document với source và build. Ví dụ dưới đây là schema minh họa do dự án tự quản lý, không phải định dạng chuẩn bắt buộc của springdoc:

~~~json
{
  "manifestVersion": 1,
  "artifact": {
    "name": "shop-openapi-public",
    "version": "1.4.2",
    "file": "shop-api-public.json",
    "mediaType": "application/vnd.oai.openapi+json",
    "sha256": "REPLACE_WITH_REAL_SHA256"
  },
  "document": {
    "title": "Shop API",
    "documentVersion": "1.4.2",
    "apiVersion": "v1",
    "openApiSpecification": "3.1.0",
    "group": "public"
  },
  "source": {
    "repository": "https://example.org/commerce/shop-service",
    "revision": "8f2a6d4c...",
    "releaseTag": "shop-api-1.4.2",
    "workingTreeClean": true
  },
  "build": {
    "runId": "ci-18452",
    "workflow": "publish-openapi",
    "builder": "company-ci",
    "jdk": "21",
    "springBoot": "3.x.y",
    "springdocOpenApi": "2.x.y",
    "generatedAt": "2026-11-20T10:30:00Z"
  },
  "ownership": {
    "team": "commerce-platform",
    "contact": "https://docs.example.org/shop/support"
  },
  "publication": {
    "uri": "https://artifacts.example.org/openapi/shop-api/1.4.2/",
    "publishedAt": "2026-11-20T10:31:00Z"
  }
}
~~~

Thay toàn bộ giá trị minh họa bằng giá trị thật trong pipeline. Không để `REPLACE_WITH_REAL_SHA256`, version placeholder hoặc commit rút gọn chưa xác minh xuất hiện trong manifest release.

Manifest nên ghi rõ group vì một ứng dụng có thể export nhiều OpenAPI document như `public`, `admin` và `partner`. Mỗi file phải có digest riêng. Nếu cùng release tạo cả JSON và YAML, ghi mỗi artifact riêng hoặc dùng một danh sách artifacts, mỗi phần tử có filename, media type và digest riêng.

## 8. Tạo checksum cho tài liệu đã sinh

Checksum giúp xác minh file nhận được có đúng byte với file đã publish hay không. Tính digest sau khi export và sau mọi bước normalize/transform cuối cùng.

Trên Linux/macOS:

~~~bash
sha256sum build/contracts/shop-api-public.json
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\build\contracts\shop-api-public.json -Algorithm SHA256
~~~

Ví dụ ghi kết quả vào file checksum:

~~~bash
sha256sum build/contracts/shop-api-public.json \
  > build/contracts/shop-api-public.json.sha256
~~~

Khi consumer tải file, họ tính lại SHA-256 và so sánh với digest được phân phối qua kênh tin cậy. Nếu hai giá trị khác nhau, file đã thay đổi hoặc quá trình tải/lưu bị lỗi; không tiếp tục generate SDK hay deploy contract từ file đó.

Checksum chỉ chứng minh hai bản có cùng nội dung byte khi digest khớp. Nếu kẻ tấn công có thể thay cả file lẫn checksum ở cùng vị trí, checksum đơn lẻ không chứng minh nguồn gốc. Với release cần bảo đảm mạnh hơn, ký manifest hoặc phát hành attestation được xác thực bằng danh tính build platform.

## 9. Liên kết checksum với đúng source revision

Một digest không cho biết source code nào tạo ra file. Manifest cần liên kết ít nhất ba thành phần:

1. Source revision: commit SHA đã checkout.
2. Build invocation: workflow, run ID, builder và các dependency/tool version.
3. Artifact subject: tên file và SHA-256 digest.

Quy trình build nên lấy commit từ CI checkout, không lấy commit hash do người dùng nhập thủ công. Ví dụ:

~~~bash
git rev-parse HEAD
git status --porcelain
git describe --tags --always
java -version
~~~

Nếu `git status --porcelain` có output, working tree không sạch. Pipeline release nên dừng hoặc ghi rõ các thay đổi bổ sung và nguồn tạo ra chúng. Không gắn tag release cho một tài liệu được sinh từ source có thay đổi chưa được commit mà không ghi nhận.

Khi build từ pull request, ghi PR number/URL và commit SHA để consumer nội bộ có thể lần ngược review. Khi build release, ghi release tag cùng commit SHA; tag giúp người đọc nhận diện release, còn commit SHA xác định chính xác nội dung source.

## 10. Ghi nhận môi trường sinh OpenAPI

Hai lần build cùng source có thể sinh document khác nhau nếu profile, cấu hình, dependency hoặc endpoint runtime khác nhau. Manifest cần ghi các đầu vào có thể làm thay đổi kết quả:

| Đầu vào | Vì sao cần ghi |
| --- | --- |
| Spring Boot version | Ảnh hưởng runtime, MVC/WebFlux và metadata được introspect |
| springdoc-openapi version | Ảnh hưởng cách đọc annotation và tạo OpenAPI model |
| swagger-core version đã resolve | Ảnh hưởng annotation/model và serialization |
| JDK version | Giúp tái tạo môi trường build |
| Maven/Gradle version | Giúp tái tạo lifecycle/task và dependency resolution |
| Active Spring profile | Có thể bật/tắt controller, bean hoặc cấu hình |
| OpenAPI group | Xác định tập operation được export |
| API docs URL/path | Xác định endpoint mà plugin tải |
| Feature flags/environment config | Có thể làm thay đổi bean hoặc route |

Không ghi secret hoặc giá trị credential vào manifest. Nếu cấu hình nhạy cảm có ảnh hưởng đến build, ghi tên secret reference hoặc tên biến môi trường và phiên bản cấu hình đã quản lý, không ghi giá trị bí mật.

Đối với môi trường có nhiều profile, nên tạo tài liệu bằng profile export đã được chuẩn hóa. Tránh để kết quả phụ thuộc vào biến môi trường không được khai báo trong build definition.

## 11. Tổ chức phiên bản tài liệu

Chọn quy tắc versioning trước khi công bố. Có thể dùng semantic versioning cho artifact OpenAPI nếu dự án định nghĩa rõ ý nghĩa từng phần:

| Mức thay đổi | Quy tắc release gợi ý | Ví dụ |
| --- | --- | --- |
| Major | Contract có thay đổi breaking hoặc consumer phải migration | `1.4.2` → `2.0.0` |
| Minor | Bổ sung contract tương thích theo policy của dự án | `1.4.2` → `1.5.0` |
| Patch | Sửa mô tả, typo hoặc metadata không làm đổi contract | `1.4.2` → `1.4.3` |

Đây là policy của tổ chức, không phải quy tắc tự động của OpenAPI. Một thay đổi nhìn có vẻ additive vẫn có thể làm hỏng consumer phụ thuộc vào enum exhaustiveness, strict schema validation hoặc generated code. Trước khi tăng minor, cần chạy compatibility checker và review consumer impact.

Nếu `info.version` được đồng bộ với artifact version, ghi quy tắc này trong release policy. Nếu không, manifest phải có cả `documentVersion`, `apiVersion` và `artifactVersion` để tránh hiểu nhầm.

Không dùng `latest` làm version duy nhất. Alias `latest` có thể trỏ đến release mới nhất để tiện xem, nhưng consumer và hệ thống production phải pin một version bất biến.

## 12. Đặt tên artifact và đường dẫn publish

Tên file cần giúp người nhận nhận biết service, group và version:

~~~text
shop-api-public-1.4.2.json
shop-api-admin-1.4.2.json
shop-api-public-1.4.2.yaml
~~~

Đường dẫn publish có thể tổ chức theo service và version:

~~~text
openapi/
  shop-api/
    1.4.1/
      shop-api-public.json
      shop-api-public.json.sha256
      provenance.json
    1.4.2/
      shop-api-public.json
      shop-api-public.json.sha256
      provenance.json
    latest/
      shop-api-public.json
~~~

Thư mục release có version là nơi lưu artifact bất biến. `latest` là alias có thể thay đổi và nên được cập nhật sau khi release versioned đã publish, verify và được phê duyệt.

Với Maven repository, có thể publish OpenAPI file như classifier hoặc artifact riêng. Với generic package registry, object storage hoặc developer portal, áp dụng cùng nguyên tắc: version nằm trong tọa độ hoặc path, metadata và checksum đi kèm, quyền truy cập được kiểm soát.

## 13. Không ghi đè artifact release đã công bố

Một release version phải luôn trỏ đến cùng nội dung. Nếu phát hiện tài liệu `1.4.2` sai:

1. Sửa source hoặc cấu hình tạo tài liệu.
2. Tạo build mới từ commit đã review.
3. Chạy validation và compatibility checks.
4. Phát hành version mới, ví dụ `1.4.3`, hoặc đánh dấu release cũ bị thu hồi theo chính sách.
5. Ghi release note nêu lý do và ảnh hưởng.

Không âm thầm upload nội dung mới đè lên `1.4.2`. Nếu một version đã được consumer tải về, thay nội dung dưới cùng version khiến checksum, cache, generated SDK và audit trail không còn đáng tin cậy.

Nếu cần sửa lỗi khẩn cấp, có thể gắn trạng thái `withdrawn` hoặc `deprecated` trong catalog/registry, giữ lại metadata của artifact cũ và công bố version thay thế. Cách xử lý cụ thể phụ thuộc artifact repository.

## 14. Phân biệt release artifact và preview artifact

Tài liệu tạo từ pull request hoặc branch chưa phát hành hữu ích cho reviewer, nhưng không nên được đặt cạnh release ổn định mà không có nhãn.

| Loại | Nguồn | Cách phân phối |
| --- | --- | --- |
| PR preview | Commit của pull request | URL có PR number và commit SHA; tự hết hạn theo retention policy |
| Branch snapshot | Branch development | Có branch và commit trong path/manifest; không xem là release |
| Release candidate | Tag hoặc commit chuẩn bị phát hành | Gắn nhãn RC, không ghi đè release ổn định |
| Stable release | Commit/tag đã được duyệt | Version bất biến, checksum và provenance đầy đủ |

Ví dụ:

~~~text
previews/pr-482/8f2a6d4c/shop-api-public.json
snapshots/develop/4c9b21e0/shop-api-public.json
releases/1.4.2/shop-api-public.json
~~~

Preview có thể được dọn theo retention policy. Release ổn định cần được lưu theo chính sách hỗ trợ và audit của tổ chức.

## 15. Quy trình publish có provenance

Một pipeline công bố tài liệu có thể tổ chức như sau:

~~~mermaid
flowchart TD
    A[Checkout commit đã review] --> B[Khởi động Spring Boot với profile export]
    B --> C[Springdoc sinh OpenAPI theo group]
    C --> D[Validate JSON/YAML và contract]
    D --> E[Tính SHA-256 cho từng artifact]
    E --> F[Tạo release manifest]
    F --> G[Ký manifest hoặc tạo provenance attestation]
    G --> H[Publish vào đường dẫn version bất biến]
    H --> I[Consumer tải và verify digest/attestation]
    I --> J[Generate SDK hoặc cập nhật developer portal]
~~~

Thứ tự có ý nghĩa:

- Tạo document từ đúng source revision đã được review.
- Validate trước khi publish để tránh phát hành file rỗng hoặc sai group.
- Tính digest sau khi mọi bước biến đổi file đã hoàn tất.
- Tạo manifest dựa trên digest thực tế, không nhập tay.
- Attestation phải tham chiếu digest của artifact cụ thể.
- Publish artifact, manifest và attestation theo một release version.
- Chỉ cập nhật alias `latest` sau khi kiểm tra release thành công.

Nếu pipeline tạo cả JSON và YAML, mỗi artifact cần digest riêng. Nếu tạo nhiều group, không dùng chung một digest hoặc một filename cho các document khác nhau.

## 16. Ký và xác minh provenance

Manifest JSON do pipeline tự ghi hữu ích cho traceability nhưng có thể bị sửa nếu người dùng có quyền ghi vào cùng artifact store. Để xác minh mạnh hơn, dùng chữ ký số hoặc attestation gắn với danh tính build platform.

SLSA/in-toto provenance có thể mô tả:

- Subject: artifact và digest của nó.
- Build definition: quy trình và tham số build.
- Resolved dependencies: source revision và dependency inputs đã resolve.
- Builder: danh tính build platform.
- Run details: metadata của lần chạy build.

Consumer cần kiểm tra cả chữ ký/danh tính builder lẫn nội dung provenance. Chỉ thấy một file tên `provenance.json` không có nghĩa đó là attestation đáng tin cậy.

Nếu dùng GitHub Actions, GitHub Artifact Attestations có thể tạo attestation liên kết artifact với repository, commit SHA và workflow. Đây là một lựa chọn theo nền tảng; các CI khác có thể dùng cơ chế ký/attestation tương đương.

Không tuyên bố tài liệu đạt một SLSA Build Level chỉ vì đã tạo checksum hoặc manifest. Mức bảo đảm phụ thuộc đầy đủ vào build platform, cách tạo attestation, tính toàn vẹn của workflow và quy trình xác minh.

## 17. Kiểm tra artifact trước khi công bố

Trước khi publish, pipeline nên kiểm tra:

- File tồn tại, không rỗng và parse được.
- Field `openapi`, `info.title`, `info.version` có giá trị phù hợp.
- Document thuộc đúng service và đúng group.
- `paths`, `components` và các `$ref` hợp lệ.
- Contact/owner và external documentation còn hiệu lực.
- Không có endpoint nội bộ hoặc schema nhạy cảm bị đưa vào bản public.
- Operation, schema và security metadata đúng với release.
- Checksum được tính từ file cuối cùng.
- Manifest trỏ đúng commit, build run, artifact name và digest.
- Publication URI trỏ đến đúng version path.

Ví dụ kiểm tra một số metadata JSON bằng jq:

~~~bash
jq -e '
  .openapi and
  .info.title == "Shop API" and
  .info.version == "1.4.2" and
  (.paths | type == "object")
' build/contracts/shop-api-public.json
~~~

Kiểm tra checksum sau khi tải:

~~~bash
sha256sum --check shop-api-public.json.sha256
~~~

Lệnh trên giả định file checksum chứa tên file tương ứng và được tải cùng thư mục. Trên Windows, dùng `Get-FileHash` rồi so sánh với digest trong manifest.

Validation cấu trúc không thay thế review bảo mật. Một OpenAPI document có thể parse thành công nhưng vẫn công bố nhầm endpoint admin hoặc header nội bộ.

## 18. Quản lý quyền truy cập tài liệu

Không phải mọi OpenAPI document đều public. Tài liệu public, partner và internal có thể chứa endpoint, hostname, schema hoặc flow bảo mật khác nhau.

Áp dụng quyền truy cập theo group và audience:

| Audience | Phạm vi tài liệu | Cách phân phối |
| --- | --- | --- |
| Public developer | Operation được phép công bố công khai | Public portal/CDN |
| Partner | Contract theo thỏa thuận tích hợp | Authenticated portal hoặc private artifact registry |
| Internal engineering | Endpoint nội bộ và vận hành | Internal portal, SSO hoặc private registry |

`@Hidden` hoặc group filter giúp quyết định operation nào xuất hiện trong document. Chúng không thay thế authorization trên HTTP endpoint. Người dùng không được phép truy cập API vẫn phải bị Spring Security/gateway từ chối, kể cả khi endpoint không có trong tài liệu.

Manifest public không nên chứa hostname nội bộ, đường dẫn filesystem, token, secret, log có dữ liệu nhạy cảm hoặc thông tin build environment không cần thiết. Tạo manifest public đã lọc metadata; giữ provenance chi tiết trong hệ thống nội bộ khi cần.

## 19. Theo dõi thay đổi và lịch sử phát hành

Mỗi release nên có release note ngắn:

~~~markdown
## Shop API 1.4.2

- Source revision: 8f2a6d4c...
- OpenAPI document: 1.4.2
- Group: public
- Artifact: shop-api-public-1.4.2.json
- SHA-256: <digest>
- Owner: commerce-platform

### Thay đổi
- Bổ sung response field estimatedDeliveryAt.
- Cập nhật mô tả lỗi validation.
- Không thay đổi endpoint hoặc request schema hiện có.
~~~

Release note giúp consumer biết lý do nên nâng version và reviewer hiểu sự khác biệt. Với thay đổi breaking, ghi rõ endpoint/field/response bị ảnh hưởng, cách migration và ngày ngừng hỗ trợ version cũ.

Lưu snapshot OpenAPI của từng release cùng manifest và release note. Khi điều tra sự cố, có thể xác định consumer đã tải document nào và đối chiếu digest thay vì dựa vào nội dung `latest` hiện tại.

## 20. Xử lý khi không xác định được nguồn gốc

Nếu nhận một OpenAPI file không có manifest hoặc không rõ owner:

1. Không suy đoán source revision từ tên file.
2. Kiểm tra `info`, contact, server URL và metadata extension nếu có.
3. Tìm artifact coordinates, release tag hoặc CI run liên quan trong registry.
4. Tính digest để cố định bản file đang điều tra.
5. Liên hệ API owner qua kênh hỗ trợ đã xác minh.
6. Chỉ đưa vào quy trình generate SDK/deploy sau khi xác nhận nguồn và compatibility.

Nếu không thể truy vết commit hoặc build, ghi nhận provenance là unknown. Không tự thêm commit SHA hoặc release version suy đoán vào manifest để làm tài liệu có vẻ đầy đủ.

## 21. Những lỗi thường gặp

**Chỉ ghi `info.version` và cho rằng đã đủ provenance.** Giá trị này không xác định source commit, builder, dependency hoặc group. Bổ sung manifest và digest.

**Chỉ ghi branch `main`.** Branch di chuyển. Lưu commit SHA và release tag.

**Dùng một version cho cả OpenAPI Specification, API và springdoc.** Đây là các version khác nhau. Ghi từng giá trị theo đúng ý nghĩa.

**Ghi owner là tên người tạo file.** Người tạo không nhất thiết là owner lâu dài. Ghi team chịu trách nhiệm và contact được duy trì.

**Manifest có digest nhưng không có chữ ký.** Digest phát hiện khác biệt byte khi có nguồn tham chiếu tin cậy; chữ ký/attestation giúp xác minh ai phát hành và artifact được tạo ra thế nào.

**Tính checksum trước khi normalize file.** Digest không còn khớp sau khi file bị thay đổi. Tính hash sau bước xử lý cuối cùng.

**Publish lại file mới dưới cùng release version.** Consumer có thể nhận nội dung khác nhau cho cùng version. Phát hành version mới hoặc đánh dấu release cũ bị thu hồi.

**Dùng `latest` trong production integration.** Alias có thể thay đổi. Pin version cụ thể và dùng latest chỉ để khám phá.

**Ghi secret hoặc thông tin nội bộ trong manifest public.** Chỉ công bố metadata cần thiết; giữ provenance chi tiết ở hệ thống private.

**Cho rằng `@Hidden` bảo vệ endpoint.** Annotation chỉ ảnh hưởng tài liệu. Dùng Spring Security/gateway để bảo vệ route thực tế.

## 22. Checklist phát hành tài liệu có thể truy vết

- [ ] Có API owner và team contact được duy trì.
- [ ] `info.title`, `info.version`, `info.contact` phản ánh đúng document.
- [ ] Đã phân biệt OpenAPI Specification version, document version và API runtime version.
- [ ] Release được tạo từ commit SHA đã review và tag rõ ràng.
- [ ] Working tree sạch hoặc mọi thay đổi bổ sung được ghi nhận.
- [ ] Manifest ghi source repository, revision, build run, tool versions và group.
- [ ] Manifest ghi artifact filename, media type, publication URI và SHA-256.
- [ ] Digest được tính sau bước export/normalize cuối cùng.
- [ ] JSON/YAML parse được và các `$ref` hợp lệ.
- [ ] Đúng group và đúng audience; không lộ endpoint/schema nội bộ.
- [ ] Artifact release được publish ở version path bất biến.
- [ ] Manifest/release note đi cùng artifact.
- [ ] Attestation/chữ ký được tạo và xác minh nếu mức bảo đảm của tổ chức yêu cầu.
- [ ] Alias `latest` chỉ được cập nhật sau khi release đã verify.
- [ ] Snapshot, manifest và release note được lưu theo retention policy.
- [ ] Có quy trình deprecate/withdraw và chuyển giao ownership.

## 23. Kết luận

Để một OpenAPI document có thể kiểm chứng và duy trì lâu dài, cần liên kết nó với owner, source revision, build environment, artifact version và publication location. Dùng `info.contact` cho đầu mối hỗ trợ; lưu commit SHA, CI run, tool versions, group và digest trong manifest; dùng checksum để phát hiện thay đổi byte và chữ ký/attestation khi cần xác minh nguồn phát hành. Publish release theo version bất biến, giữ snapshot cùng release note và chỉ dùng `latest` như alias. Nhờ đó, consumer có thể xác định chính xác tài liệu nào đã được công bố, ai chịu trách nhiệm và nó được tạo ra từ source nào.

## 24. Nguồn tham khảo

- [OpenAPI Specification 3.1 — Info Object](https://spec.openapis.org/oas/v3.1.1.html#info-object): ý nghĩa `info.version`, contact, description và metadata của OpenAPI document.
- [OpenAPI Specification 3.1 — Specification Extensions](https://spec.openapis.org/oas/v3.1.1.html#specification-extensions): cách mở rộng document bằng field có tiền tố `x-`.
- [SLSA — Build Provenance](https://slsa.dev/spec/v1.2/build-provenance): liên kết artifact với build definition, dependencies, builder và run details.
- [SLSA — Provenance](https://slsa.dev/spec/v1.2/provenance): khái niệm provenance và khả năng truy vết artifact về nguồn tạo.
- [GitHub Docs — Artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations): provenance và integrity guarantees cho artifact.
- [GitHub Docs — Using artifact attestations to establish provenance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): tạo attestation cho artifact từ workflow và subject path.
- [springdoc-openapi — Getting Started](https://springdoc.org/getting-started.html): cách springdoc tích hợp Spring Boot và sinh OpenAPI document từ ứng dụng.
