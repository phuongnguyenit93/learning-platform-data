# Theo dõi vòng đời runtime và kế hoạch nâng cấp dependency

Một function serverless có thể chạy ổn định hôm nay nhưng trở thành rủi ro trong vài tháng tới nếu Java runtime hết hỗ trợ, framework không còn nhận bản vá, thư viện có lỗ hổng hoặc container base image đã lỗi thời. Việc nâng cấp vì thế là một phần của vận hành và quản trị hệ thống, không chỉ là công việc bảo trì định kỳ của nhóm phát triển.

Với Java serverless, cần theo dõi nhiều lớp vòng đời riêng biệt:

- Runtime và hệ điều hành do cloud provider quản lý.
- Phiên bản Java/JDK và vendor distribution.
- Framework, thư viện trực tiếp và dependency bắc cầu.
- Build tool, compiler plugin và công cụ đóng gói.
- Container base image, runtime agent và native library.
- Function configuration, deployment artifact và các integration contract.

Một ứng dụng có thể dùng Java 21 nhưng vẫn không an toàn nếu Spring Boot, logging library hoặc base image chứa lỗ hổng. Ngược lại, cập nhật một dependency có thể làm thay đổi hành vi serialization, connection pool hoặc startup, ảnh hưởng trực tiếp tới function đang chạy ở quy mô lớn.

Bài học này trình bày cách lập inventory, theo dõi end-of-support, đánh giá lỗ hổng, xây dựng kế hoạch nâng cấp, kiểm thử tương thích và triển khai từng bước để duy trì Java serverless an toàn và có thể kiểm toán.

## 1. Vòng đời runtime và dependency là gì?

Vòng đời phần mềm mô tả các giai đoạn từ phát hành, bảo trì, nhận bản vá, chuyển sang trạng thái hạn chế hỗ trợ cho tới khi hết hỗ trợ hoặc bị loại bỏ.

Các mốc thường gặp:

| Mốc | Ý nghĩa | Hành động quản trị |
|---|---|---|
| General availability | Phiên bản được phát hành chính thức | Đánh giá, kiểm thử và đưa vào danh mục được phép |
| Active support | Nhận sửa lỗi và cập nhật theo chính sách vendor | Theo dõi release và security advisory |
| Maintenance support | Phạm vi sửa lỗi có thể bị giới hạn | Lập kế hoạch chuyển phiên bản |
| End of standard support | Hết giai đoạn hỗ trợ tiêu chuẩn | Xác định thời hạn nâng cấp và ngoại lệ |
| End of life/end of support | Không còn bản vá hoặc hỗ trợ thông thường | Nâng cấp hoặc có biện pháp giảm thiểu được phê duyệt |
| Runtime deprecation | Provider bắt đầu ngừng hỗ trợ runtime trong dịch vụ | Chuyển sang runtime được hỗ trợ |
| Runtime retirement | Runtime không còn được dùng để deploy hoặc vận hành theo chính sách dịch vụ | Hoàn tất migration trước thời hạn |

Tên và thứ tự các mốc khác nhau giữa nhà cung cấp. Một vendor có thể dùng các trạng thái deprecated, blocked for new deployments và blocked for updates vào các thời điểm khác nhau. Không suy ra rằng runtime ngừng tạo function thì function đang chạy cũng tự động dừng ngay; phải đọc policy cụ thể.

### 1.1. Bốn vòng đời cần theo dõi riêng

| Lớp | Ví dụ | Nguồn vòng đời |
|---|---|---|
| Cloud runtime | AWS Lambda managed Java runtime, Azure Functions runtime, Google Cloud Functions runtime | Cloud provider |
| Java platform | OpenJDK build, Oracle JDK, Amazon Corretto, Microsoft Build of OpenJDK, Eclipse Temurin | JDK vendor/distribution |
| Application dependencies | Spring Boot, Jackson, Netty, Log4j, AWS SDK | Project/vendor maintainers |
| Build/deployment stack | Maven, Gradle, plugins, container base image, buildpack | Tool/image maintainers |

Không gộp các mốc này thành một trường Java version. Một function có thể dùng Java runtime được provider hỗ trợ nhưng dependency đã hết support; hoặc dependency còn được hỗ trợ nhưng runtime provider sắp retirement.

## 2. Runtime do cloud provider quản lý và runtime tự đóng gói

Có hai cách triển khai phổ biến.

**Managed runtime:** function chọn một runtime Java do cloud provider cung cấp. Provider quản lý phần lớn runtime environment, cập nhật hệ điều hành/runtime theo policy dịch vụ và công bố lịch deprecation/retirement.

**Custom runtime hoặc container image:** nhóm phát triển đóng gói runtime, JDK/JRE, thư viện hệ thống và ứng dụng vào artifact hoặc image. Nhóm chịu trách nhiệm theo dõi và cập nhật nhiều thành phần hơn, bao gồm base image, package hệ điều hành, JDK và native library.

| Khía cạnh | Managed runtime | Custom runtime/container |
|---|---|---|
| Cập nhật runtime nền | Provider quản lý theo policy | Nhóm ứng dụng/build pipeline quản lý |
| Quyền kiểm soát phiên bản | Theo danh sách provider hỗ trợ | Chủ động chọn phiên bản |
| Trách nhiệm patch OS | Thường thuộc provider | Thuộc người duy trì image |
| SBOM | Có thể cần kết hợp thông tin provider và artifact ứng dụng | Có thể tạo cho toàn bộ image/artifact |
| Rủi ro | Bị ảnh hưởng bởi lịch retirement hoặc runtime update | Quên rebuild image hoặc giữ package lỗi thời |
| Kiểm thử | Cần xác minh behavior trước/sau runtime update | Cần kiểm thử cả runtime, image và application |

Managed runtime giảm công việc vận hành nhưng không xóa trách nhiệm quản trị dependency của ứng dụng. Container giúp kiểm soát môi trường nhưng tăng trách nhiệm cập nhật và chứng minh nguồn gốc artifact.

### 2.1. Runtime update tự động

Một số nền tảng áp dụng runtime security update tự động; một số cung cấp chế độ kiểm soát thời điểm cập nhật hoặc runtime management setting. Cần xác định:

- Provider cập nhật runtime vào thời điểm nào?
- Có thể trì hoãn hoặc ghim runtime version hay không?
- Runtime update có thể thay đổi patch level mà không đổi cấu hình function không?
- Có thông báo trước khi runtime bị deprecate/retire không?
- Có cần redeploy để nhận bản vá không?
- Function có thể tiếp tục chạy nhưng không được tạo deployment mới không?
- Cách kiểm tra runtime version thực tế trong môi trường đang chạy?

Không mặc định managed runtime luôn tự động nhận mọi bản vá ngay lập tức. Đọc tài liệu runtime management của dịch vụ và kiểm tra thông tin version thực tế.

## 3. Lập inventory runtime và dependency

Không thể quản trị vòng đời nếu không biết tổ chức đang chạy phiên bản nào. Bước đầu là tạo inventory cho mọi function và artifact liên quan.

Thông tin nên ghi nhận:

| Trường | Ví dụ |
|---|---|
| Service/function | orders-worker |
| Owner/team | commerce-platform |
| Environment | production |
| Provider/region | AWS / ap-southeast-1 |
| Deployment type | Managed runtime / container |
| Runtime | Java 21 |
| JDK vendor | Amazon Corretto |
| Framework | Spring Boot 3.x |
| Build tool | Maven |
| Artifact version | orders-worker 2.8.4 |
| Base image | Image name + immutable digest |
| Direct dependencies | AWS SDK, Jackson, Micrometer |
| Deployment date | Ngày phát hành hiện tại |
| Support deadline | Ngày cần hoàn thành migration |
| Criticality | Tier 1 / Tier 2 / Tier 3 |
| Data classification | Public / Internal / Confidential / Restricted |
| Owner of exception | Người phê duyệt ngoại lệ nếu có |

Không chỉ kiểm kê function production. Cần biết cả function staging, preview, scheduled jobs, DLQ replay workers, migration utilities và function ít được gọi. Một function không có traffic vẫn có thể chứa code hoặc secret và trở thành điểm rủi ro.

### 3.1. Tự động hóa inventory

Có thể kết hợp:

- Cloud resource inventory/configuration API.
- Infrastructure-as-code state.
- Deployment manifest.
- Build artifact metadata.
- Container registry metadata.
- SBOM từ pipeline.
- Cloud asset inventory và organization policy.

Đối chiếu các nguồn để phát hiện function được tạo thủ công hoặc artifact đã deploy nhưng không có source owner. Ghi lại ngày cập nhật gần nhất và nguồn dữ liệu để người vận hành biết inventory có còn mới không.

### 3.2. Phân loại mức độ quan trọng

Không phải mọi function đều cần cùng thời hạn nâng cấp. Có thể phân loại theo:

- Có xử lý payment, identity hoặc dữ liệu nhạy cảm không?
- Có public HTTP endpoint không?
- Có quyền IAM rộng hoặc truy cập nhiều hệ thống không?
- Có nằm trên luồng giao dịch quan trọng không?
- Có xử lý event có thể replay không?
- Có yêu cầu compliance hoặc audit đặc biệt không?
- Có khả năng bị khai thác từ internet hoặc message untrusted không?

Function public, có quyền cao hoặc xử lý dữ liệu nhạy cảm cần ưu tiên đánh giá rủi ro cao hơn.

## 4. Theo dõi Java release và JDK vendor

Java có nhiều bản phát hành feature và các bản cập nhật bảo mật/critical patch theo lịch của từng vendor. Phiên bản được gọi là LTS thường có thời gian hỗ trợ dài hơn theo chính sách của vendor, nhưng LTS không có nghĩa mọi JDK distribution đều có cùng thời hạn hoặc cùng cam kết hỗ trợ.

Khi chọn Java version, cần kiểm tra:

- Java feature release đang dùng.
- Vendor distribution và support policy.
- Ngày kết thúc hỗ trợ của vendor.
- Security update cadence.
- Kiến trúc CPU được hỗ trợ.
- Compatibility với cloud runtime.
- Compatibility với framework và library.
- Hỗ trợ build tool và test agent.
- Khả năng chạy trên local, CI và production giống nhau.

Không chỉ ghi Java 21 trong inventory. Hãy ghi cả distribution/vendor và patch/build level khi nguồn dữ liệu cho phép.

### 4.1. LTS không phải là lý do duy nhất để nâng cấp

Chọn một Java LTS mới có thể mang lại thời gian hỗ trợ dài, hiệu năng hoặc tính năng mới. Nhưng việc chuyển version cũng có thể làm thay đổi:

- Bytecode target và compiler behavior.
- Reflection, module access và encapsulation.
- TLS/security defaults.
- Garbage collector và memory behavior.
- JIT compilation và startup profile.
- Serialization hoặc library compatibility.
- Native agent, JNI và GraalVM compatibility.

Lập kế hoạch dựa trên thời hạn support, security risk, compatibility và giá trị kỹ thuật. Không nâng cấp chỉ vì version number mới hơn; cũng không trì hoãn đến sát EOL mới bắt đầu.

## 5. Theo dõi framework và dependency bắc cầu

Dependency trực tiếp là thư viện được khai báo trong project. Dependency bắc cầu là thư viện được kéo vào thông qua dependency khác.

Ví dụ:

~~~text
orders-worker
  -> spring-boot-starter-web
       -> spring-web
       -> spring-context
       -> spring-core
       -> jackson-databind
       -> logging implementation
  -> cloud provider SDK
       -> HTTP client
       -> authentication library
       -> JSON library
~~~

Một dependency bắc cầu có thể chứa CVE dù nhóm phát triển không khai báo trực tiếp nó. Vì vậy, chỉ review pom.xml hoặc build.gradle chưa đủ; cần phân tích dependency graph thực tế của artifact.

Các thành phần nên kiểm kê:

- Framework và framework starters.
- JSON/XML parser.
- HTTP client và TLS provider.
- Logging facade và implementation.
- Database driver và connection pool.
- Cloud SDK và authentication library.
- Serialization, compression và archive library.
- Metrics/tracing agent.
- Native library và JNI binding.
- Test/build plugin có thể chạy trong CI.

### 5.1. Dependency management và version alignment

Với Maven, dùng dependency management/BOM để quản lý version đồng bộ. Với Gradle, dùng platform/version catalog và dependency locking phù hợp.

Mục tiêu:

- Tránh nhiều module dùng version khác nhau ngoài chủ ý.
- Hạn chế version conflict.
- Làm dependency graph có thể tái tạo.
- Dễ nâng cấp framework và SDK theo bộ tương thích.
- Ghi lại lý do khi phải override version do security patch.

Không ép một transitive dependency lên version mới chỉ vì scanner đề xuất nếu framework chưa tương thích. Xác minh release notes và chạy test trước khi override.

## 6. Build tool, plugin và container base image cũng có vòng đời

Nâng Java runtime mà giữ Maven/Gradle wrapper quá cũ có thể gây lỗi build hoặc không hỗ trợ compiler mới. Plugin compiler, test, shade, packaging và native image cũng cần được quản trị.

Với container:

- Ghi image name và digest.
- Theo dõi distro/package manager và base image support.
- Rebuild từ base image đã vá.
- Kiểm tra package hệ điều hành và native library.
- Không dùng tag floating như latest làm định danh artifact production.
- Scan image sau build và trước deploy.
- Giữ artifact provenance và build metadata.

Nếu base image được cập nhật nhưng function không được rebuild, production vẫn chạy image cũ. Chỉ theo dõi tag trong Dockerfile không đủ; cần inventory digest đang được deploy.

## 7. SBOM: biết chính xác artifact chứa gì

Software Bill of Materials (SBOM) là danh mục thành phần phần mềm có trong một artifact. SBOM giúp biết package nào, version nào và quan hệ dependency nào đang được phân phối.

Hai định dạng phổ biến:

- **CycloneDX:** thường dùng cho component inventory, dependency relationship và security use cases.
- **SPDX:** định dạng chuẩn để biểu diễn thông tin thành phần, license và provenance.

Một SBOM có thể chứa:

- Component name và version.
- Package URL (PURL) hoặc identifier.
- Supplier/vendor.
- License.
- Dependency relationship.
- Hash/checksum.
- Metadata về tool tạo SBOM.
- Artifact/build reference.

Ví dụ rút gọn minh họa:

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "components": [
    {
      "type": "library",
      "name": "jackson-databind",
      "version": "2.x.y",
      "purl": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.x.y"
    }
  ]
}
~~~

Đây là dữ liệu minh họa, không phải SBOM thực của project. Version cụ thể phải lấy từ artifact được build.

### 7.1. SBOM cho Java function

Với Maven/Gradle, tạo SBOM từ dependency graph của release artifact. Với container image, tạo hoặc bổ sung inventory package OS và runtime layer. SBOM của source dependency không nhất thiết mô tả chính xác nội dung image production nếu shading, relocation, packaging hoặc image layering làm thay đổi artifact.

Gắn SBOM với:

- Artifact checksum.
- Git commit.
- Build pipeline/run ID.
- Image digest.
- Function version/revision.
- Deployment environment.

Lưu SBOM cùng release evidence để khi có CVE mới có thể truy vấn function nào đang chứa package bị ảnh hưởng.

## 8. Quét lỗ hổng và quản lý CVE

Công cụ Software Composition Analysis (SCA) đối chiếu package/version với vulnerability database và advisory. Kết quả có thể bao gồm CVE, severity, affected range, fixed version và dependency path.

Các nguồn thường được dùng:

- GitHub Security Advisories.
- NVD.
- OSV.
- Advisory từ vendor framework/library.
- Cloud provider security bulletin.
- Container registry/image scanning.
- SCA tool trong CI hoặc artifact registry.

Mỗi nguồn có thời điểm cập nhật và mức độ bao phủ khác nhau. Một kết quả không tìm thấy CVE không chứng minh package an toàn tuyệt đối.

### 8.1. CVSS không phải toàn bộ quyết định ưu tiên

CVSS giúp mô tả mức độ nghiêm trọng kỹ thuật, nhưng không thể hiện đầy đủ mức rủi ro trong môi trường triển khai cụ thể.

Khi ưu tiên CVE, xem xét:

- Có phiên bản bị ảnh hưởng trong artifact thực tế không?
- Code path dễ bị tổn thương có được sử dụng không?
- Function có public exposure không?
- Attacker có thể kiểm soát input không?
- Function có quyền IAM hoặc dữ liệu nhạy cảm nào?
- Có exploit công khai hoặc bằng chứng khai thác thực tế không?
- Có bản vá chính thức không?
- Có workaround an toàn không?
- Có yêu cầu pháp lý/contract về thời hạn xử lý không?

Một CVE critical trong package không được load có thể có mức rủi ro thực tế khác với CVE high trong parser xử lý input public. Tuy nhiên, không dùng "không thấy code path" làm lý do miễn trừ nếu chưa có phân tích đáng tin cậy.

### 8.2. Phân loại quyết định

| Kết quả đánh giá | Hành động |
|---|---|
| Affected và exploit dễ tiếp cận | Ưu tiên patch khẩn cấp hoặc giảm exposure ngay |
| Affected, có bản vá tương thích | Lập hotfix/upgrade và triển khai nhanh |
| Affected, chưa có bản vá | Mitigate, theo dõi advisory và đặt deadline review |
| Không affected theo version/config | Lưu bằng chứng và lý do loại trừ |
| False positive | Ghi nhận scanner rule, package path và bằng chứng |
| Không rõ phạm vi ảnh hưởng | Điều tra thêm, không tự đánh dấu resolved |

Không đóng ticket CVE chỉ vì scanner hết cảnh báo sau khi đổi tên package hoặc suppress rule. Cần lưu bằng chứng version/artifact và lý do.

## 9. Chính sách thời hạn xử lý lỗ hổng

Tổ chức nên định nghĩa SLA xử lý theo mức độ rủi ro. Các con số cụ thể do governance/security policy phê duyệt, không có một lịch chung áp dụng cho mọi công ty.

Ví dụ khung policy minh họa:

| Mức ưu tiên | Ví dụ điều kiện | Hướng xử lý |
|---|---|---|
| Emergency | Exploit đang được khai thác, public exposure, impact nghiêm trọng | Triage ngay, giảm exposure và hotfix |
| Critical | CVE nghiêm trọng, component có mặt trong production | Ưu tiên patch trong thời hạn ngắn được policy quy định |
| High | Có thể khai thác trong context của service | Đưa vào sprint ưu tiên và theo dõi deadline |
| Medium | Khả năng khai thác hoặc impact hạn chế hơn | Lên kế hoạch trong chu kỳ bảo trì |
| Low | Rủi ro thấp, không có path tiếp cận rõ | Theo dõi và cập nhật theo lịch |

SLA cần phân biệt thời gian acknowledge, triage, mitigation và permanent fix. Nếu chưa có bản vá, việc giảm exposure có thể là mitigation tạm thời nhưng không nên tự động coi là remediation hoàn tất.

## 10. Theo dõi runtime deprecation và EOL

Mỗi runtime/provider cần một record lifecycle với các trường:

- Runtime name và version.
- Provider service và region.
- Ngày bắt đầu hỗ trợ.
- Ngày deprecation.
- Hạn chế deployment mới.
- Hạn chế cập nhật function hiện có.
- Ngày retirement.
- Thay thế được khuyến nghị.
- Link đến thông báo chính thức.
- Owner migration.
- Trạng thái và deadline nội bộ.

Các mốc provider có thể thay đổi. Cần định kỳ đọc thông báo chính thức và cập nhật inventory; không sao chép ngày EOL từ một blog cũ.

### 10.1. Lập lịch cảnh báo trước EOL

Có thể chia thành các checkpoint nội bộ:

- **T-180 ngày:** inventory impacted functions, chọn target runtime và ước lượng effort.
- **T-120 ngày:** kiểm tra framework/library compatibility, tạo migration branch và test plan.
- **T-90 ngày:** deploy thử ở development/staging, sửa incompatibility.
- **T-60 ngày:** canary hoặc rollout một phần production.
- **T-30 ngày:** hoàn thành phần lớn migration, theo dõi ngoại lệ.
- **Trước deadline:** xác minh không còn function production chạy runtime sắp retirement.

Đây là lịch mẫu để tổ chức điều chỉnh. Runtime có thể được deprecate với thời hạn ngắn hơn hoặc có quy tắc khác; luôn dùng thông báo provider làm nguồn chính.

Không đợi đến ngày runtime bị chặn deploy mới bắt đầu migration. Thời gian cần thiết còn phụ thuộc số function, framework, integration và quy trình phê duyệt.

## 11. Lập kế hoạch nâng cấp theo dependency graph

Không nên nâng tất cả thư viện lên version mới cùng lúc mà không hiểu quan hệ tương thích. Bắt đầu bằng dependency graph và phân nhóm thay đổi.

Ví dụ thứ tự thường gặp:

1. Chọn Java target runtime/JDK được hỗ trợ.
2. Nâng build tool và compiler/test plugin để build trên JDK mục tiêu.
3. Nâng framework/BOM lên phiên bản hỗ trợ Java mục tiêu.
4. Nâng cloud SDK và integration library.
5. Nâng dependency trực tiếp và bắc cầu còn lại.
6. Rebuild container base image hoặc custom runtime.
7. Chạy unit, integration, contract và load tests.
8. Tạo SBOM/scan lại artifact.
9. Deploy canary và quan sát.
10. Rollout hoàn tất và xác minh inventory.

Thứ tự thực tế có thể khác. Framework có thể yêu cầu JDK mới trước, hoặc provider runtime cần được chuyển trước khi nâng framework. Ghi dependency constraints và release note làm căn cứ.

### 11.1. Chia nhỏ upgrade để giảm phạm vi lỗi

Một đợt nâng cấp có thể bao gồm nhiều thay đổi độc lập:

- Java major version.
- Framework major version.
- Logging implementation.
- HTTP client.
- Database driver.
- Cloud SDK.
- Base image.

Nếu tất cả thay đổi trong một release, khi lỗi xảy ra khó xác định nguyên nhân. Với hệ thống lớn, tách thành các đợt có thể kiểm soát. Với CVE khẩn cấp, có thể cần một hotfix nhỏ chỉ cập nhật component bị ảnh hưởng.

## 12. Compatibility checklist cho Java serverless

Trước khi nâng Java hoặc framework, kiểm tra:

**Build và bytecode**

- Compiler source/release target.
- Maven/Gradle wrapper.
- Compiler, Surefire/Failsafe và packaging plugin.
- Annotation processor và code generation.
- Shading/relocation.
- Dependency convergence và duplicate classes.

**Runtime**

- Provider hỗ trợ Java version và architecture.
- JVM flags và memory limits.
- TLS/cipher defaults.
- Reflection và module access.
- Classpath/module path.
- Timezone, locale và trust store.
- JNI/native library.

**Framework và integration**

- Dependency injection và startup hooks.
- HTTP serialization/deserialization.
- Validation và exception mapping.
- Database driver và connection pool.
- Cloud SDK authentication/credential chain.
- Metrics, logging và tracing agent.
- Function handler signature và event model.

**Serverless behavior**

- Cold start/init duration.
- Timeout và memory.
- Concurrency và thread lifecycle.
- Connection reuse giữa invocation.
- Environment variable/configuration.
- Temporary storage và file system.
- Shutdown hook và graceful termination.
- Retry, idempotency và partial batch response.

Một bản nâng cấp có thể compile thành công nhưng vẫn thay đổi runtime behavior. Cần test trên cùng loại runtime/container và trigger thực tế.

## 13. Thử nghiệm Java major upgrade

Khi chuyển từ một Java LTS sang LTS tiếp theo, kiểm tra các khu vực có rủi ro:

- API bị deprecated hoặc removed.
- Reflection vào internal JDK API.
- Strong encapsulation và module access.
- Garbage collector và heap sizing.
- TLS defaults và certificate handling.
- Charset/locale/timezone behavior.
- Serialization compatibility.
- Threading và executor behavior.
- JIT warm-up, startup và memory footprint.
- Agent/profiler/APM compatibility.

Chạy test suite với target JDK mới ở CI trước khi đổi production runtime. Nếu có thể, build một artifact giống production và chạy integration test trên provider runtime hoặc container image mục tiêu.

### 13.1. Build JDK và runtime JRE

Build JDK và runtime image có thể khác nhau. Điều này hợp lệ nếu đã kiểm soát:

- Bytecode target.
- Vendor compatibility.
- Native library architecture.
- Required modules.
- Runtime classpath.
- Security provider/trust store.
- Build provenance.

Không mặc định ứng dụng build thành công trên JDK mới thì runtime cũ sẽ chạy được, hoặc ngược lại. Kiểm tra bytecode và API thực sự được dùng.

## 14. Nâng framework và thư viện

Framework major upgrade thường có breaking changes trong cấu hình, auto-configuration, dependency baseline và API. Đọc migration guide/release notes của framework trước khi thay version.

Với Spring Boot hoặc framework tương tự, kiểm tra:

- Java baseline được hỗ trợ.
- Dependency BOM và version được quản lý.
- Deprecated configuration property.
- HTTP server/embedded container version.
- Jackson/JSON behavior.
- Validation namespace/API.
- Security filter chain và default behavior.
- Observability instrumentation.
- Startup/lazy initialization.
- Native image/AOT compatibility nếu sử dụng.

Không override một dependency do framework quản lý mà không kiểm tra matrix tương thích. Một patch security riêng lẻ có thể cần framework patch release thay vì nâng một transitive library độc lập.

## 15. Nâng container base image

Với function đóng gói dạng container, image lifecycle là một phần của runtime lifecycle.

Quy trình:

1. Xác định base image và digest đang deploy.
2. Kiểm tra distro, package và JDK build.
3. Đọc advisory của image vendor.
4. Chọn image đã được cập nhật và còn support.
5. Rebuild application image từ source và lockfile.
6. Scan image và SBOM.
7. Test startup, handler, native library và security settings.
8. Push image bất biến, ghi digest.
9. Deploy revision/canary.
10. Lưu bằng chứng scan và image digest đã chạy.

Ví dụ Dockerfile minh họa:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/orders-worker.jar /app/app.jar

USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Tag image trong ví dụ chỉ minh họa lựa chọn base image. Trong production, pin image bằng digest và quy trình update digest có kiểm soát; tag có thể trỏ tới nội dung mới theo thời gian.

Không chạy ứng dụng bằng root nếu không cần. Giữ image nhỏ giúp giảm bề mặt tấn công và thời gian pull, nhưng không được loại bỏ package cần thiết cho TLS, timezone hoặc native runtime.

## 16. Tự động hóa kiểm tra trong CI/CD

Pipeline có thể kiểm tra dependency và runtime ở nhiều thời điểm:

**Pull request**

- Compile với JDK mục tiêu.
- Unit và integration tests.
- Dependency graph diff.
- SCA scan.
- License policy.
- Secret scanning.
- Kiểm tra build reproducibility.

**Build/release**

- Tạo SBOM.
- Scan artifact và container image.
- Kiểm tra base image support.
- Ký artifact/image nếu policy yêu cầu.
- Tạo provenance/attestation.
- Lưu commit, toolchain và dependency lock state.

**Deploy**

- Xác minh runtime được phép.
- Kiểm tra security gate.
- Kiểm tra target environment và region.
- Canary/smoke test.
- Theo dõi error, latency, cold start và memory.
- Ghi deployment revision và artifact digest.

**Định kỳ**

- Rescan SBOM với vulnerability feed mới.
- Kiểm tra runtime EOL.
- Kiểm tra dependency đã hết support.
- Phát hiện image digest cũ.
- Tìm function không có owner hoặc không được deploy từ pipeline chuẩn.

SCA scan tại build chỉ phản ánh dữ liệu vulnerability tại thời điểm đó. Một CVE mới có thể được công bố sau khi artifact đã deploy; cần rescan SBOM đang chạy, không chỉ scan source khi build.

## 17. Ví dụ kiểm tra dependency bằng Maven

Các lệnh sau minh họa việc xem dependency tree và kiểm tra version được resolve:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
./mvnw -DskipTests=false verify
~~~

dependency:tree giúp tìm dependency bắc cầu và đường dẫn đưa package vào project. effective-pom cho biết version/configuration sau khi áp dụng parent và BOM. Các lệnh này không tự xác định CVE; kết hợp với SCA tool và advisory database.

Với Gradle, có thể dùng:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind
./gradlew test
~~~

Dependency locking và version catalog giúp kiểm soát version đã resolve. Lưu lockfile theo quy trình của project để build có thể tái tạo.

## 18. Kiểm thử sau nâng cấp

Một bộ kiểm thử nâng cấp runtime/dependency nên có:

| Nhóm test | Điều cần xác minh |
|---|---|
| Unit | Logic nghiệp vụ và edge case không đổi |
| Integration | Database, HTTP client, serialization và SDK |
| Contract | Event schema, API request/response và compatibility |
| Security | TLS, authentication, IAM, deserialization và scanner |
| Startup | Cold start, init duration và readiness |
| Load | Throughput, p95/p99, memory và GC |
| Resilience | Retry, timeout, idempotency, redelivery và DLQ |
| Regression | Kết quả nghiệp vụ so với phiên bản trước |
| Deployment | Artifact, image digest, environment config và rollback |
| Observability | Log, metric, trace và alert vẫn hoạt động |

Đối với queue consumer, gửi message thử và xác minh ack, retry, partial batch failure, visibility/ack deadline và duplicate behavior. Đối với HTTP function, kiểm tra response status, headers, authentication và timeout.

Đừng chỉ xác minh function trả 200. Kiểm tra side effect và business state để phát hiện lỗi âm thầm.

## 19. Canary và rollout theo từng giai đoạn

Một bản nâng cấp runtime có thể ảnh hưởng đến toàn bộ function sau khi deploy. Canary giúp phát hiện lỗi trên một phần traffic trước khi rollout rộng.

Một chiến lược tổng quát:

~~~mermaid
flowchart TD
    A["Build artifact mới + SBOM"] --> B["Security and compatibility gates"]
    B --> C["Deploy dev/staging"]
    C --> D["Integration and load tests"]
    D --> E["Canary một phần traffic"]
    E --> F{"SLO và correctness đạt?"}
    F -->|Có| G["Tăng dần traffic"]
    G --> H["Rollout hoàn tất"]
    F -->|Không| I["Dừng rollout / rollback"]
    I --> J["Điều tra và tạo bản sửa"]
~~~

Có thể sử dụng các cơ chế tương ứng của nền tảng:

- AWS Lambda version + alias với weighted routing.
- Cloud Run revision và traffic splitting.
- Azure Functions deployment slots hoặc cơ chế rollout phù hợp hosting plan.
- Container platform deployment strategy như rolling hoặc blue/green.

Tên tính năng và giới hạn phụ thuộc dịch vụ/plan. Chọn cơ chế được nền tảng hỗ trợ và kiểm tra cách rollback thực tế.

### 19.1. Tiêu chí canary

Theo dõi ít nhất:

- Invocation success/error rate.
- Timeout và throttling.
- p50/p95/p99 duration.
- Cold start/init duration.
- Memory/CPU và GC.
- Downstream latency.
- Queue age/backlog.
- Retry và DLQ.
- Business outcome và duplicate side effect.

So sánh candidate với baseline cùng traffic profile. Nếu canary chỉ nhận một loại request đơn giản, nó có thể bỏ sót lỗi ở payload hoặc integration hiếm gặp.

### 19.2. Rollback có giới hạn

Rollback code không luôn đảo ngược được database migration hoặc external side effect. Trước rollout cần kiểm tra:

- Database schema có tương thích ngược không?
- Event schema có backward/forward compatibility không?
- Có thay đổi format dữ liệu đã ghi không?
- Có thay đổi IAM policy hoặc secret version không?
- Provider SDK có tạo side effect không thể đảo ngược không?
- Artifact cũ có còn sẵn để deploy lại không?

Dùng expand-contract cho database schema: thêm cột/field tương thích, deploy code hỗ trợ cả schema cũ và mới, chuyển traffic, rồi mới loại bỏ phần cũ sau khi không còn consumer sử dụng.

## 20. Quản trị dependency exception

Đôi khi chưa thể nâng cấp ngay vì dependency không có bản vá tương thích hoặc provider chưa hỗ trợ runtime mục tiêu. Ngoại lệ phải có thời hạn và chủ sở hữu.

Một record exception nên có:

- Component/version bị ảnh hưởng.
- CVE hoặc lý do chưa thể nâng cấp.
- Function/artifact/environment bị ảnh hưởng.
- Exposure và business impact.
- Mitigation đang áp dụng.
- Owner kỹ thuật.
- Người phê duyệt rủi ro.
- Ngày bắt đầu và ngày hết hạn.
- Điều kiện để đóng exception.
- Link tới ticket và bằng chứng.

Không để exception vĩnh viễn hoặc chỉ ghi "will upgrade later". Mỗi lần gia hạn cần đánh giá lại exploitability, exposure và mitigation.

## 21. Chính sách runtime và dependency được phép

Tổ chức có thể duy trì một catalog nội bộ gồm:

- Java versions được phép cho production.
- JDK vendor/distribution được phê duyệt.
- Cloud managed runtime được hỗ trợ.
- Framework baseline.
- Dependency có license được phép.
- Base image đã được scan và support.
- Build tool/plugin version.
- Security configuration bắt buộc.
- Quy trình xin exception.

Policy nên phân biệt:

- **Allowed:** có thể dùng trong production.
- **Preferred:** phiên bản được khuyến nghị cho project mới.
- **Deprecated:** còn hoạt động nhưng không nên dùng cho deployment mới.
- **Blocked:** không được deploy production.
- **Exception:** chỉ được dùng khi có phê duyệt và deadline.

Không chỉ block version trong CI. Cần inventory production để tìm resource cũ đã deploy trước khi policy được áp dụng.

## 22. Audit evidence và khả năng truy xuất

Khi kiểm toán hoặc xử lý sự cố bảo mật, đội vận hành cần chứng minh artifact nào đang chạy, được build từ source nào và chứa dependency nào.

Lưu các bằng chứng:

- Source commit và pull request.
- Build pipeline identity và timestamp.
- Build tool/JDK version.
- Dependency lockfile.
- SBOM.
- SCA scan report và CVE disposition.
- Artifact checksum/image digest.
- Signature/provenance nếu có.
- Approval và exception record.
- Deployment revision/version.
- Runtime configuration và provider runtime identifier.
- Canary result và rollback history.

Không lưu secret hoặc dữ liệu production nhạy cảm trong audit evidence. Dùng metadata, checksum và reference đến hệ thống có quyền truy cập phù hợp.

### 22.1. Truy xuất từ CVE tới function

Khi có advisory mới:

1. Lấy package name/PURL và affected version range.
2. Query SBOM registry để tìm artifact chứa package.
3. Map artifact tới function/revision đang chạy.
4. Xác định environment, region, owner và exposure.
5. Đánh giá exploitability và impact.
6. Tạo remediation task theo SLA.
7. Theo dõi deploy version đã vá.
8. Xác minh runtime production không còn artifact bị ảnh hưởng.
9. Lưu evidence và đóng finding.

Cần giữ quan hệ giữa artifact, image digest và deployment revision. Nếu chỉ biết source repository, có thể bỏ sót function đang chạy artifact cũ.

## 23. Ví dụ kế hoạch nâng cấp một Java function

Giả sử orders-worker đang dùng:

- Managed Java runtime sắp tới thời hạn deprecation.
- Spring Boot baseline cũ.
- Cloud SDK có một dependency bắc cầu bị cảnh báo.
- Function xử lý SQS message và ghi database.

Kế hoạch:

**Giai đoạn 1 — Discover**

- Liệt kê function, runtime, framework, JDK vendor và artifact version.
- Tạo SBOM của production artifact.
- Xác định affected dependency và runtime target được provider hỗ trợ.
- Đặt owner và deadline.

**Giai đoạn 2 — Plan**

- Chọn Java target version và framework version tương thích.
- Nâng Maven/Gradle wrapper và compiler plugin.
- Xử lý dependency bị ảnh hưởng theo BOM hoặc patch release.
- Xác định schema/event compatibility.
- Chuẩn bị test matrix và rollback plan.

**Giai đoạn 3 — Build and verify**

- Build trên JDK mục tiêu.
- Chạy unit/integration/contract test.
- Kiểm tra SQS event model, partial batch failure và idempotency.
- Đo cold start, memory, duration và throughput.
- Tạo SBOM mới và scan artifact/image.

**Giai đoạn 4 — Deploy**

- Deploy staging và chạy smoke/load test.
- Deploy canary một phần traffic.
- Theo dõi error rate, queue age, DLQ và business state.
- Tăng traffic theo các bước đã định.

**Giai đoạn 5 — Close**

- Xác minh mọi production revision chạy runtime/dependency được hỗ trợ.
- Lưu build, scan, approval và deployment evidence.
- Cập nhật inventory.
- Đóng exception và CVE ticket.
- Xóa runtime/artifact cũ theo retention policy.

## 24. Lịch governance định kỳ

Một lịch tham khảo:

| Chu kỳ | Hoạt động |
|---|---|
| Mỗi build | Dependency/SCA scan, unit test và SBOM |
| Mỗi release | Compatibility, image scan, provenance và deployment evidence |
| Hàng ngày | Ingest security advisory và phát hiện CVE mới |
| Hàng tuần | Review critical/high findings và runtime deadline gần |
| Hàng tháng | Reconcile runtime inventory, dependency support và owner |
| Hàng quý | Review Java LTS roadmap, framework baseline và exception |
| Trước EOL | Migration, canary, rollback test và xác minh production fleet |

Chu kỳ cần điều chỉnh theo mức độ rủi ro và yêu cầu compliance. Critical vulnerability hoặc runtime retirement có thể cần xử lý ngay, không đợi kỳ review tiếp theo.

## 25. Các lỗi quản trị thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra Java major version | Bỏ sót framework và transitive CVE | Inventory toàn bộ dependency graph |
| Chỉ scan khi build | CVE mới không được phát hiện ở artifact đang chạy | Rescan SBOM định kỳ |
| Không biết runtime provider deadline | Bị chặn deploy hoặc buộc migration gấp | Lifecycle calendar và owner |
| Dùng floating container tag | Không biết chính xác image production | Pin digest và lưu provenance |
| Nâng nhiều major dependency cùng lúc | Khó xác định nguyên nhân regression | Chia upgrade thành các đợt |
| Không test trên runtime đích | Lỗi chỉ xuất hiện sau deploy | Integration test trên provider/container tương ứng |
| Suppress CVE không có lý do | Rủi ro bị che khuất | Exception có evidence và expiry |
| Rollback code nhưng schema không tương thích | Service cũ không chạy với schema mới | Expand-contract migration |
| Không lưu SBOM/artifact digest | Khó xác định fleet bị ảnh hưởng | Gắn evidence với deployment revision |
| Chỉ quản lý production | Function cũ ở staging/utility vẫn có lỗ hổng | Inventory toàn bộ environment |

## 26. Quy trình theo dõi vòng đời và nâng cấp dependency

1. **Inventory.** Liệt kê function, runtime, JDK vendor, framework, dependency, build tool và image digest.
2. **Assign owner.** Mỗi component và function cần có team chịu trách nhiệm.
3. **Track support dates.** Theo dõi release, deprecation, EOL và retirement từ nguồn chính thức.
4. **Generate SBOM.** Gắn SBOM với artifact checksum và deployment revision.
5. **Scan continuously.** Quét dependency và image ở CI, registry và định kỳ sau deploy.
6. **Triage risk.** Kết hợp severity, exploitability, exposure, data sensitivity và business criticality.
7. **Plan upgrade.** Chọn target version tương thích, chia nhỏ thay đổi và đặt deadline.
8. **Test.** Chạy build, integration, contract, security, load và serverless behavior tests.
9. **Canary.** Deploy một phần traffic, so sánh với baseline.
10. **Rollback safely.** Kiểm tra code, schema, event và external side effect trước khi rollback.
11. **Verify fleet.** Xác minh mọi production function đã chạy runtime/artifact được hỗ trợ.
12. **Retain evidence.** Lưu SBOM, scan, approval, artifact digest và deployment record.
13. **Review exceptions.** Gia hạn hoặc đóng ngoại lệ dựa trên rủi ro hiện tại.

## 27. Câu hỏi tự kiểm tra

- Runtime provider, Java JDK và application dependency có những vòng đời khác nhau như thế nào?
- Managed runtime và custom container phân chia trách nhiệm patch ra sao?
- Vì sao inventory phải ghi JDK vendor và artifact digest?
- Dependency bắc cầu có thể đưa CVE vào function như thế nào?
- SBOM giúp truy vấn production fleet khi có CVE mới ra sao?
- CVSS khác risk assessment theo exposure như thế nào?
- Vì sao cần rescan SBOM sau khi artifact đã deploy?
- Runtime deprecation khác retirement như thế nào?
- Những bước nào cần có trước khi nâng Java major version?
- Vì sao phải kiểm tra framework BOM và dependency convergence?
- Container base image cần được pin và rebuild như thế nào?
- Canary nên theo dõi những metric và business outcome nào?
- Vì sao rollback code có thể thất bại sau database schema migration?
- Một dependency exception cần có owner, mitigation và expiry ra sao?
- Audit evidence nào giúp truy xuất CVE tới function/revision đang chạy?


