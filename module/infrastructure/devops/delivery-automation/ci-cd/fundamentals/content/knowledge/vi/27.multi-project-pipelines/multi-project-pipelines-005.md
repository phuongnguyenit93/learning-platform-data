# Thiết kế pipeline dùng lại mà vẫn cho phép cấu hình rõ ràng

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích lợi ích và giới hạn của việc chuẩn hóa CI/CD cho nhiều repository hoặc nhiều dự án.
- Phân biệt pipeline template, reusable workflow, composite action/task module và shared pipeline library.
- Xác định phần quy trình nên dùng chung và phần khác biệt cần được khai báo theo từng dự án.
- Thiết kế contract đầu vào, đầu ra, quyền, secret và artifact cho một pipeline dùng lại.
- Tổ chức cấu hình theo schema, giá trị mặc định, profile và override có quy tắc.
- Tạo extension point để dự án bổ sung bước riêng mà không sao chép toàn bộ pipeline.
- Quản lý version, compatibility, deprecation và quá trình nâng cấp pipeline dùng chung.
- Kiểm thử, quan sát và quản trị pipeline dùng chung trên nhiều dự án.

## 1. Vì sao cần pipeline dùng lại?

Khi một tổ chức có nhiều repository, mỗi nhóm thường tự xây dựng pipeline cho lint, test, build, scan, publish và deploy. Ban đầu các pipeline có thể khá giống nhau, nhưng theo thời gian chúng dần khác biệt:

- Repository này kiểm tra dependency, repository khác quên bước đó.
- Một dự án publish artifact bằng digest, dự án khác dùng tag có thể bị ghi đè.
- Quyền token và cách lấy secret không thống nhất.
- Một lỗi trong workflow được sửa ở một repository nhưng các repository khác vẫn còn lỗi.
- Khi chính sách bảo mật thay đổi, platform team phải sửa nhiều file.
- Người mới không biết đâu là bước bắt buộc và đâu là tùy chọn riêng của dự án.

Pipeline dùng lại giúp chuẩn hóa những phần có ý nghĩa chung, giảm sao chép và làm cho thay đổi quy trình có thể được quản lý tập trung.

Tuy nhiên, không phải mọi dự án đều giống nhau. Một thư viện Java, một dịch vụ Spring Boot, một frontend SPA và một worker xử lý message có thể cần bước build, test, package và deploy khác nhau. Nếu ép tất cả vào một workflow với hàng chục điều kiện ẩn, pipeline sẽ khó hiểu hơn các bản sao ban đầu.

Mục tiêu là tạo **một quy trình chuẩn có contract rõ ràng, cấu hình tường minh và điểm mở rộng được kiểm soát**.

Một pipeline dùng lại tốt cần trả lời được:

- Bước nào mọi dự án bắt buộc phải thực hiện?
- Dự án cần cung cấp những thông tin gì?
- Những khác biệt nào được cấu hình?
- Dự án có thể bổ sung bước riêng ở đâu?
- Quyền và secret được cấp theo nguyên tắc nào?
- Khi pipeline dùng chung thay đổi, dự án nào bị ảnh hưởng?
- Làm thế nào kiểm chứng một cấu hình dự án trước khi chạy?

## 2. Nguyên tắc: chuẩn hóa quy trình, khai báo khác biệt

Nên bắt đầu bằng cách phân loại các phần của pipeline.

**Phần dùng chung** thường gồm:

- Xác định source revision và pipeline context.
- Thiết lập môi trường build theo chuẩn.
- Khôi phục dependency theo cơ chế được tổ chức chấp nhận.
- Chạy các kiểm tra bắt buộc.
- Thu thập và xác minh report.
- Tạo artifact có định danh bất biến.
- Gắn provenance và metadata.
- Áp dụng quality gate.
- Publish evidence và deployment record.
- Kiểm soát quyền, secret và audit.

**Phần có thể khác theo dự án** thường gồm:

- Ngôn ngữ và runtime.
- Build tool và lệnh build.
- Danh sách module hoặc package.
- Bộ test cần chạy.
- Phiên bản runtime được hỗ trợ.
- Artifact type và cách đóng gói.
- Môi trường deploy và chiến lược rollout.
- Các kiểm tra đặc thù nghiệp vụ.
- Tài nguyên hoặc dependency cần cho integration test.

**Phần không nên cho dự án tùy ý thay đổi** thường là:

- Chính sách quyền tối thiểu.
- Cách xác minh nguồn gốc artifact.
- Điều kiện bắt buộc trước production.
- Cách bảo vệ secret.
- Quy tắc lưu audit và evidence.
- Các kiểm soát ngăn chạy mã không tin cậy với quyền cao.

Có thể hình dung kiến trúc:

~~~mermaid
flowchart TD
    A["Project repository"] --> B["Project pipeline config"]
    B --> C["Reusable pipeline contract"]
    C --> D["Shared build and test workflow"]
    C --> E["Shared security and evidence workflow"]
    C --> F["Shared release and deploy workflow"]
    D --> G["Project artifact"]
    E --> H["Quality decision"]
    G --> H
    H --> I["Release workflow"]
    I --> J["Deployment and verification"]
    K["Organization policy"] --> C
    K --> H
~~~

Repository cung cấp cấu hình và source. Pipeline dùng chung thực thi các quy tắc đã được định nghĩa. Policy của tổ chức kiểm soát những điều kiện không được tùy tiện bỏ qua.

## 3. Các mức tái sử dụng pipeline

Không phải mọi phần dùng chung đều cần đóng gói theo cùng một cách. Có bốn hình thức phổ biến.

| Hình thức | Cách hoạt động | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|---|
| Pipeline template | Tạo bộ file ban đầu để repository sao chép | Muốn chuẩn hóa cấu trúc khởi tạo | Sau khi sao chép, các bản có thể drift |
| Reusable workflow | Workflow này gọi workflow dùng chung | Cần tập trung logic và cập nhật có kiểm soát | Cần thiết kế input/output và quyền rõ |
| Composite action/task module | Đóng gói một nhóm bước nhỏ | Muốn tái sử dụng thao tác ở cấp job/step | Không nên gom toàn bộ lifecycle vào một action khó quan sát |
| Shared pipeline library/plugin | Chia sẻ hàm hoặc abstraction cho nhiều pipeline | Nền tảng có cơ chế library/plugin phù hợp | Cần quản lý API và version chặt chẽ |

### 3.1. Pipeline template

Template tạo ra một cấu trúc khởi đầu gồm workflow, cấu hình và tài liệu. Repository có thể điều chỉnh bản sao theo nhu cầu.

Ưu điểm:

- Dễ hiểu vì file nằm ngay trong repository.
- Dự án có quyền kiểm soát thay đổi.
- Không phụ thuộc runtime vào một workflow bên ngoài.

Giới hạn:

- Các bản sao có thể dần khác nhau.
- Việc cập nhật policy cần đồng bộ hoặc có công cụ kiểm tra drift.
- Sửa lỗi ở template không tự sửa các repository đã tạo trước đó.

Template phù hợp cho bootstrap hoặc khi nền tảng không hỗ trợ gọi workflow dùng chung.

### 3.2. Reusable workflow

Reusable workflow giữ logic ở một nơi và cho repository gọi bằng contract. Đây thường là lựa chọn phù hợp khi nhiều dự án cần cùng một quy trình có version.

Ưu điểm:

- Sửa logic tập trung.
- Dễ kiểm soát version.
- Có thể chuẩn hóa quyền và evidence collection.
- Giảm sao chép giữa repository.

Giới hạn:

- Cần hiểu input, output, secret và permission propagation.
- Một thay đổi có thể ảnh hưởng nhiều consumer.
- Debug cần xem cả caller và workflow được gọi.

Nên giữ reusable workflow ở mức một trách nhiệm rõ ràng, ví dụ build-and-test, publish-artifact hoặc deploy-environment. Có thể có một workflow điều phối cấp cao gọi các workflow chuyên trách.

### 3.3. Composite action hoặc task module

Đây là đơn vị tái sử dụng nhỏ hơn, thường đóng gói một thao tác như:

- Resolve toolchain.
- Validate project manifest.
- Tải report theo run ID.
- Tính digest và tạo evidence manifest.
- Kiểm tra artifact provenance.
- Publish deployment record.

Chúng phù hợp khi logic cần dùng ở nhiều workflow nhưng không cần đóng gói cả một pipeline lifecycle.

Một action nhỏ nên có đầu vào và đầu ra đơn giản. Nếu một action tự cài tool, build, test, publish, deploy và gửi thông báo, nó sẽ che giấu quá nhiều hành vi và khó xác định lỗi.

### 3.4. Shared library hoặc plugin

Một số nền tảng cho phép dùng thư viện pipeline, plugin hoặc task framework. Hình thức này có thể phù hợp khi tổ chức cần abstraction phức tạp, logic có thể kiểm thử như code và nhiều pipeline dùng chung.

Cần quản lý:

- API công khai.
- Version và compatibility.
- Dependency của library.
- Quyền khi library được thực thi.
- Cách debug và xác định library revision đã chạy.

Không nên tạo abstraction riêng nếu reusable workflow hoặc action có sẵn đã đáp ứng yêu cầu.

## 4. Xác định ranh giới dùng chung

Trước khi xây reusable pipeline, hãy xem các pipeline hiện có và tìm phần lặp lại thực sự.

Có thể nhóm theo capability:

- Source preparation.
- Build và test.
- Security analysis.
- Artifact publishing.
- Release verification.
- Deployment.
- Post-deploy verification.
- Evidence collection.

Một quy trình chung không nhất thiết phải là một file duy nhất. Chia theo capability giúp consumer chỉ gọi phần cần thiết và giảm coupling.

Ví dụ:

| Capability | Dùng chung | Cấu hình dự án |
|---|---|---|
| Build | Chuẩn hóa log, cache, artifact upload | Build tool, command, module |
| Test | Thu thập report, tổng hợp kết quả | Test suite, profile, runtime |
| Security | Scanner và policy baseline | Scope hoặc exception có phê duyệt |
| Package | Đặt metadata, tính digest | Artifact type và package coordinates |
| Publish | Quyền, registry validation, evidence | Registry/project namespace được cho phép |
| Deploy | Preflight, approval, verification | Target environment và strategy được cho phép |

Một phần chỉ nên trừu tượng hóa khi có ít nhất một lý do rõ: được dùng lại ở nhiều nơi, có quy tắc cần thống nhất, hoặc có thay đổi cần quản lý tập trung.

Không nên tạo reusable abstraction chỉ vì hai file có vài dòng giống nhau. Nếu khác biệt về hành vi lớn hơn phần chung, một module nhỏ hoặc template có thể phù hợp hơn.

## 5. Thiết kế contract đầu vào

Contract là giao diện giữa repository gọi pipeline và workflow dùng chung.

Input cần có:

- Tên và ý nghĩa rõ ràng.
- Kiểu dữ liệu.
- Bắt buộc hay tùy chọn.
- Giá trị mặc định nếu có.
- Miền giá trị hoặc allowlist.
- Điều kiện tương thích.
- Cách validate.
- Mức độ nhạy cảm nếu là secret reference.

Ví dụ:

| Input | Kiểu | Bắt buộc | Quy tắc |
|---|---|---|---|
| project_type | Enum | Có | service, library, frontend, worker |
| runtime_version | String/Enum | Có | Chỉ nhận phiên bản được hỗ trợ |
| build_tool | Enum | Có | maven, gradle, npm hoặc tool được cho phép |
| build_command | String | Có hoặc theo profile | Phải nằm trong contract của project |
| test_profile | Enum | Không | Mặc định theo project_type |
| artifact_name | String | Có | Không chứa đường dẫn tùy ý |
| deploy_target | Enum | Không | Chỉ nhận environment đã khai báo |
| deployment_strategy | Enum | Không | Chỉ nhận strategy được target hỗ trợ |

Tránh các input mơ hồ như mode, custom, extra hoặc options nếu không có schema mô tả chính xác. Một input có tên chung nhưng có thể thay đổi mọi hành vi sẽ khiến workflow khó review và khó bảo đảm.

Không nhận một chuỗi lệnh shell tùy ý từ repository rồi thực thi với quyền publish hoặc production. Nếu cần custom command, chạy nó trong job có quyền tối thiểu và không nhận secret nhạy cảm. Các bước phát hành đặc quyền nên được tách riêng.

## 6. Contract đầu ra và trạng thái

Pipeline dùng lại cần cung cấp đầu ra để workflow phía sau sử dụng mà không phải đọc log hoặc suy đoán tên file.

Các output hữu ích:

- source_commit.
- pipeline_run_id.
- project_id.
- artifact_uri.
- artifact_digest.
- build_result.
- test_summary.
- evidence_manifest_uri.
- quality_gate_decision.
- release_id.
- deployment_id.
- deployment_status.

Cần xác định rõ semantics của output:

- Output có luôn được tạo không?
- Có thể rỗng không?
- Được tạo ở job nào?
- Có chứa secret không?
- Có thể dùng làm input cho downstream workflow không?
- Có gắn với attempt hiện tại không?

Một workflow có thể kết thúc với trạng thái success nhưng artifact output không tồn tại nếu publish bị skip. Vì vậy output contract cần phân biệt success, skipped, failed, partial và unavailable.

Không nên yêu cầu consumer parse câu chữ trong log để lấy artifact version. Dùng output có cấu trúc và schema/version rõ ràng.

## 7. Cấu hình rõ ràng theo dự án

Một repository nên có file cấu hình mô tả các lựa chọn được phép. Cấu hình nên dễ đọc, được review cùng source và có thể validate trước khi pipeline thực thi.

Ví dụ cấu trúc:

~~~text
project/
├── .ci/
│   ├── pipeline.yml
│   └── schema/
│       └── pipeline-config.schema.json
├── src/
├── tests/
└── build files
~~~

Ví dụ file cấu hình:

~~~yaml
pipeline:
  schema_version: 1

  project:
    name: billing-service
    type: service
    owner: payments-team

  build:
    tool: gradle
    runtime: "21"
    command: "./gradlew clean build"
    modules:
      - api
      - application

  tests:
    unit:
      enabled: true
      command: "./gradlew test"
    integration:
      enabled: true
      profile: ci

  artifact:
    type: container
    name: billing-service

  deployment:
    enabled: true
    targets:
      - staging
      - production
    strategy:
      staging: rolling
      production: canary
~~~

Đây là cấu trúc minh họa, không phải schema của một công cụ CI cụ thể. Các trường cần được định nghĩa và validate bằng schema của tổ chức.

File cấu hình không nên chứa token, password, private key hoặc credential. Chỉ lưu tên secret reference hoặc identity profile nếu thực sự cần và đã được allowlist.

## 8. Schema validation và lỗi cấu hình sớm

Cấu hình sai nên được phát hiện trước khi pipeline bắt đầu build hoặc nhận quyền triển khai.

Schema có thể kiểm tra:

- Trường bắt buộc.
- Kiểu dữ liệu.
- Enum hợp lệ.
- Pattern của tên.
- Giá trị số trong range.
- Cấu trúc lồng nhau.
- Trường không được phép.
- Tương quan giữa các trường.

Ví dụ:

- project_type là library thì deploy.enabled phải false.
- artifact.type là container thì cần image name.
- deployment.enabled là true thì phải có ít nhất một target.
- deployment.strategy phải được target hỗ trợ.
- Runtime version phải thuộc danh sách platform hỗ trợ.
- Integration test bật thì cần khai báo test profile hoặc service dependency.

Có thể dùng JSON Schema, CUE, schema YAML hoặc validator riêng. Dù chọn công cụ nào, cần version hóa schema và thông báo lỗi đủ rõ để project owner biết trường nào sai.

Nên ưu tiên fail fast. Không nên để pipeline chạy build 15 phút rồi mới phát hiện project_type không hợp lệ hoặc target production không được phép.

## 9. Quy tắc precedence và nguồn cấu hình

Cấu hình có thể đến từ nhiều lớp:

1. Organization policy.
2. Shared pipeline defaults.
3. Project configuration.
4. Environment-specific configuration.
5. Runtime input được phép.
6. Secret manager hoặc identity provider.

Nếu không quy định thứ tự ưu tiên, hai dự án có thể hiểu cùng một cấu hình theo cách khác nhau.

Một mô hình tham khảo:

- Organization policy đặt các giới hạn không thể bị override.
- Shared workflow cung cấp default an toàn.
- Project config khai báo đặc điểm build/test.
- Environment config cung cấp endpoint, quota và deployment strategy được cho phép.
- Runtime input chỉ chọn trong danh sách đã khai báo.
- Secret manager cung cấp giá trị bí mật theo identity.

Không nên để runtime input ghi đè organization policy. Ví dụ repository không được tự đặt security_scan.required=false nếu scanner là yêu cầu bắt buộc của tổ chức.

Nên ghi lại cấu hình đã resolve, schema version và policy revision trong pipeline evidence. Điều này giúp giải thích vì sao một lần chạy có hành vi khác lần trước.

## 10. Phân biệt cấu hình với logic

Cấu hình nên mô tả lựa chọn; workflow chứa logic thực thi.

Ví dụ, cấu hình chọn runtime Java 21. Workflow chịu trách nhiệm cài đúng toolchain, xác minh phiên bản và chạy build.

Cấu hình chọn deployment strategy là canary. Workflow kiểm tra target có hỗ trợ canary, lấy quyền phù hợp, thực hiện rollout và đánh giá metric.

Nếu cấu hình bắt đầu chứa nhiều script, điều kiện lồng nhau và logic nghiệp vụ, có thể đã biến file config thành một ngôn ngữ lập trình khó kiểm soát.

Một số nguyên tắc:

- Cấu hình chọn trong tập hành vi được hỗ trợ.
- Logic dùng chung thực hiện hành vi.
- Policy xác định hành vi nào được phép.
- Extension point xử lý trường hợp đặc thù có lý do.
- Secret được lấy từ secret manager.
- Giá trị resolve được ghi nhận để truy vết.

Không nên dùng một biến boolean cho quá nhiều ý nghĩa. Ví dụ skip_checks có thể vô tình bỏ qua cả lint, test và security scan. Nên dùng các lựa chọn riêng có tên rõ và policy tương ứng.

## 11. Profiles cho nhóm dự án

Một số dự án có đặc điểm giống nhau. Có thể tạo profile để giảm cấu hình lặp:

- java-library.
- java-service.
- frontend-spa.
- container-worker.
- serverless-function.

Profile cung cấp default phù hợp, nhưng vẫn phải thể hiện rõ giá trị nào được kế thừa và giá trị nào được project override.

Ví dụ:

~~~yaml
pipeline:
  profile: java-service

  overrides:
    build:
      runtime: "21"

    tests:
      integration:
        enabled: true

    deployment:
      targets:
        - staging
        - production
~~~

Không nên tạo quá nhiều profile cho từng repository. Profile nên đại diện cho một nhóm kiến trúc hoặc lifecycle ổn định, không phải một cách đặt tên khác cho mỗi dự án.

Khi profile thay đổi, cần ghi profile version hoặc resolved configuration để biết pipeline run đã dùng bộ default nào.

## 12. Extension point có kiểm soát

Một số dự án cần bước riêng mà pipeline dùng chung không thể bao quát. Có thể hỗ trợ extension point, nhưng phải giới hạn rõ vị trí và quyền.

Ví dụ extension point hợp lý:

- Pre-build validation không có quyền publish.
- Custom test job chạy trong môi trường cô lập.
- Post-build verification chỉ đọc artifact.
- Pre-deploy check chỉ đọc trạng thái target.
- Post-deploy smoke test trong phạm vi được cấp.

Một extension point cần xác định:

- Khi nào được gọi.
- Input và output.
- Timeout.
- Runner/permission scope.
- Secret nào được phép dùng.
- Điều kiện success/failure.
- Có được block pipeline không.
- Cách thu thập log và report.

Không nên cho dự án chèn tùy ý lệnh trước hoặc sau mọi bước đặc quyền. Một custom hook chạy trước publish mà được cấp token ghi registry có thể trở thành đường để mã tùy ý phát hành artifact.

Với extension có quyền cao, cần review, pin revision và policy riêng. Có thể dùng một workflow riêng được bảo vệ hoặc một reusable component đã được platform team phê duyệt.

## 13. Tách build/test khỏi publish/deploy có quyền cao

Một pipeline dùng chung không nên cấp mọi quyền cho mọi job chỉ vì một giai đoạn cuối cần publish hoặc deploy.

Có thể chia thành các vùng:

- Validation jobs: đọc source, chạy test và scan.
- Build job: tạo artifact trong runner được kiểm soát.
- Evidence job: tổng hợp report và provenance.
- Publish job: quyền ghi vào đúng registry/project.
- Deploy job: identity riêng cho môi trường đích.

Project config có thể chọn build tool hoặc test profile, nhưng không nên tự cấp thêm quyền ghi registry hay quyền production.

Các quyền cần được giới hạn theo:

- Repository/project.
- Job hoặc workflow.
- Branch/tag được bảo vệ.
- Artifact repository.
- Environment.
- Thời hạn credential.
- Action cụ thể được phép thực hiện.

Nếu nền tảng hỗ trợ OIDC hoặc workload identity, nên dùng credential ngắn hạn theo claim được xác minh. Secret tĩnh cần được scope theo job và môi trường, không truyền xuyên suốt mọi workflow.

## 14. Reusable pipeline và artifact contract

Các workflow dùng chung nên trao đổi bằng artifact reference và digest.

Ví dụ build workflow trả về:

~~~yaml
outputs:
  artifact:
    uri: registry.example.invalid/team/billing-service
    digest: sha256:0123456789abcdef
  source:
    commit: 8f4c2a1
  evidence:
    manifest_uri: evidence://release-123/manifest.json
~~~

Đây là dữ liệu minh họa. Trong hệ thống thực tế, digest phải được tạo từ artifact thật và output phải được bảo vệ theo trust model.

Downstream deploy workflow nên nhận artifact digest trực tiếp. Không nên tìm artifact mới nhất bằng tag mutable hoặc dựa vào tên file trong workspace của job trước.

Một artifact contract cần nêu:

- Registry và repository được phép.
- Digest format.
- Metadata bắt buộc.
- Provenance hoặc signature policy.
- Retention.
- Quy tắc promotion qua môi trường.
- Hành vi khi artifact bị thu hồi.

Điều này giúp một reusable deploy workflow có thể triển khai artifact từ nhiều dự án mà vẫn xác minh được nguồn gốc.

## 15. Versioning pipeline dùng chung

Reusable workflow là một dependency của repository consumer. Khi workflow thay đổi, hành vi pipeline của consumer cũng có thể thay đổi.

Cần version hóa:

- Reusable workflow.
- Composite action/task module.
- Shared library/plugin.
- Configuration schema.
- Project profile.
- Policy bundle.

Có thể dùng semantic versioning khi contract có quy tắc tương thích rõ:

- Patch: sửa lỗi không thay đổi contract.
- Minor: thêm tính năng tương thích ngược.
- Major: thay đổi input/output hoặc semantics có thể làm consumer cũ hỏng.

Nếu nền tảng hỗ trợ, pin reusable component bằng tag version được bảo vệ hoặc commit SHA bất biến. Với production pipeline, pin revision giúp tái lập hành vi và điều tra.

Không nên tham chiếu một nhánh mutable như main cho mọi consumer production nếu không có quy trình kiểm soát thay đổi. Consumer cần biết chính xác revision nào đã chạy.

## 16. Thay đổi contract và quản lý tương thích

Khi muốn đổi tên input, xóa output hoặc thay đổi default, cần có lộ trình.

Một quy trình an toàn:

1. Thêm input mới nhưng giữ input cũ.
2. Hỗ trợ cả hai trong một khoảng chuyển tiếp.
3. Cảnh báo consumer còn dùng input cũ.
4. Cập nhật project config và kiểm thử.
5. Công bố version có thay đổi contract.
6. Chỉ xóa input cũ ở major version tiếp theo.
7. Lưu migration guide và thời hạn hỗ trợ.

Cần đặc biệt chú ý thay đổi default. Đổi default từ test profile A sang B có thể làm pipeline của hàng chục dự án thay đổi hành vi dù file config không đổi.

Vì vậy default cũng là một phần contract và cần versioning. Pipeline run nên ghi resolved config để có thể giải thích kết quả lịch sử.

## 17. Quản lý adoption và nâng cấp consumer

Khi có phiên bản reusable pipeline mới, không nên cập nhật mọi repository một cách mù quáng.

Có thể triển khai theo các giai đoạn:

- Internal test repositories.
- Một số dự án đại diện có cấu trúc khác nhau.
- Nhóm dự án pilot.
- Mở rộng theo team hoặc portfolio.
- Theo dõi lỗi và rollback version nếu cần.

Mỗi consumer nên có:

- Pipeline version đang dùng.
- Config schema version.
- Project owner.
- Ngày nâng cấp gần nhất.
- Trạng thái tương thích.
- Exception đang tồn tại.
- Link đến migration guide.

Có thể dùng bot hoặc automation để mở pull request nâng version, nhưng cần kiểm tra build/test và review theo policy. Việc mở PR không đồng nghĩa consumer đã được nâng cấp.

Đối với thay đổi bắt buộc vì bảo mật, cần có deadline và cách xác định consumer chưa cập nhật. Không nên duy trì vô thời hạn các version đã hết hỗ trợ.

## 18. Kiểm thử reusable pipeline

Pipeline dùng chung là code vận hành nhiều dự án. Cần kiểm thử contract và hành vi, không chỉ kiểm tra file YAML parse được.

Các lớp kiểm thử:

**Schema tests**

- Cấu hình hợp lệ được chấp nhận.
- Trường sai kiểu bị từ chối.
- Giá trị enum không hợp lệ bị từ chối.
- Tổ hợp trường mâu thuẫn bị từ chối.
- Secret không được phép xuất hiện trong file config.

**Contract tests**

- Input/output đúng schema.
- Output artifact có digest.
- Report gắn với đúng run.
- Quyền không bị mở rộng ngoài contract.
- Lỗi được truyền về caller đúng trạng thái.

**Integration tests**

- Workflow chạy với một project mẫu cho từng profile.
- Artifact được tạo và publish vào registry thử nghiệm.
- Evidence collector nhận đủ report.
- Deployment vào môi trường test có thể xác minh và rollback.

**Compatibility tests**

- Consumer cũ vẫn hoạt động với version mới trong phạm vi được hỗ trợ.
- Config schema mới xử lý đúng config cũ.
- Breaking change bị phát hiện trước khi release.

**Security tests**

- Job không tin cậy không nhận secret đặc quyền.
- Input không thể chọn target ngoài allowlist.
- Reusable component được pin theo revision.
- Custom hook không thể lấy quyền của publish/deploy job.

Nên duy trì một số fixture repository đại diện cho service, library, frontend và worker để kiểm thử thay đổi pipeline.

## 19. Quan sát pipeline dùng chung

Khi một pipeline dùng lại được dùng bởi nhiều repository, cần phân biệt lỗi của shared workflow với lỗi cấu hình hoặc source của consumer.

Các thông tin nên ghi:

- Shared workflow name và version/SHA.
- Project/repository ID.
- Config schema và profile version.
- Resolved configuration fingerprint.
- Pipeline run ID và attempt.
- Job và step thất bại.
- Artifact digest.
- Policy revision.
- Runner image và toolchain version.
- Consumer-specific extension đã chạy.
- Kết quả gate và deployment.

Có thể theo dõi các chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| Adoption rate | Tỷ lệ repository dùng version được hỗ trợ |
| Upgrade lag | Thời gian consumer chậm nâng cấp |
| Workflow failure rate | Tỷ lệ lỗi của reusable workflow |
| Config validation failures | Lỗi cấu hình trước khi chạy |
| Time to repair | Thời gian sửa lỗi shared pipeline |
| Exception count | Số dự án cần ngoại lệ |
| Version distribution | Các revision đang được sử dụng |
| Pipeline duration by profile | Hiệu năng theo nhóm dự án |

Nếu một version mới làm tăng failure rate ở nhiều repository, có thể lỗi nằm ở shared workflow. Nếu chỉ một project thất bại với config validation, cần kiểm tra cấu hình hoặc profile của project đó.

## 20. Governance và quyền sở hữu

Pipeline dùng chung thường có nhiều bên liên quan:

- Platform team sở hữu reusable workflow và runner.
- Security team sở hữu policy hoặc baseline scan.
- Project team sở hữu source và project config.
- Release owner chịu trách nhiệm quyết định phát hành.
- Operations team sở hữu môi trường và deployment controls.

Cần xác định rõ:

- Ai được thay đổi shared workflow?
- Ai review thay đổi có ảnh hưởng security?
- Ai phát hành version mới?
- Ai được phê duyệt exception?
- Ai chịu trách nhiệm cập nhật consumer?
- Ai xử lý sự cố do pipeline dùng chung?
- Ai có quyền thay đổi production policy?

Không nên để một project team có thể sửa policy tập trung chỉ bằng cách thay file config trong repository của họ. Policy bắt buộc cần được quản lý ở nơi có quyền phù hợp.

Một mô hình ownership rõ giúp giảm thời gian điều tra khi nhiều dự án cùng gặp một lỗi.

## 21. Ví dụ luồng gọi pipeline dùng chung

YAML sau minh họa một repository khai báo cấu hình và gọi các workflow dùng chung. Cú pháp thực tế phụ thuộc nền tảng CI/CD.

~~~yaml
project:
  name: billing-service
  profile: java-service
  config_schema: 2

pipeline:
  shared_components:
    build_and_test: v3.2.0
    security_analysis: v2.4.1
    publish_artifact: v1.8.0
    deploy: v4.1.0

  build:
    runtime: "21"
    tool: gradle
    modules:
      - api
      - application

  tests:
    unit: true
    integration:
      enabled: true
      profile: ci

  artifact:
    type: container
    repository: team/billing-service

  deployment:
    staging:
      enabled: true
      strategy: rolling
    production:
      enabled: true
      strategy: canary
      approval: required
~~~

Một luồng tổng quát:

~~~mermaid
flowchart TD
    A["Project config"] --> B["Schema validation"]
    B --> C["Resolve defaults and policy"]
    C --> D["Build and test workflow"]
    D --> E["Security and evidence workflow"]
    E --> F["Artifact digest + manifest"]
    F --> G["Publish workflow"]
    G --> H["Release gate"]
    H --> I["Deploy workflow"]
    I --> J["Post-deploy verification"]
~~~

Điểm quan trọng là project config chọn những khả năng được hỗ trợ và khai báo các khác biệt có chủ đích. Shared workflow vẫn kiểm soát logic thực thi, policy và quyền.

## 22. Anti-pattern khi thiết kế pipeline dùng lại

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Một workflow khổng lồ cho mọi dự án | Nhiều nhánh điều kiện và khó debug | Chia reusable workflow theo capability |
| Copy template rồi không cập nhật | Consumer drift khỏi chuẩn | Theo dõi version và drift |
| Input là chuỗi shell tùy ý | Thực thi mã với quyền không rõ | Dùng enum/contract và job quyền tối thiểu |
| Quá nhiều boolean skip | Không biết bước bắt buộc nào đã bị bỏ qua | Cấu hình riêng từng capability và policy |
| Default thay đổi âm thầm | Pipeline consumer đổi hành vi mà config không đổi | Version hóa default và ghi resolved config |
| Reusable workflow dùng branch mutable | Không tái lập được lần chạy | Pin tag được bảo vệ hoặc SHA |
| Dự án tự cấp production secret | Tăng phạm vi quyền và rủi ro lộ | Environment identity và approval tập trung |
| Hook tùy ý chạy trong job publish | Mã dự án có thể lấy quyền đặc quyền | Tách hook khỏi job có quyền cao |
| Không có contract output | Consumer parse log hoặc tìm file theo tên | Output có cấu trúc và schema |
| Xóa input cũ ngay lập tức | Nhiều consumer bị hỏng | Deprecation và migration window |
| Chỉ test workflow trên một repository | Bỏ sót khác biệt profile | Fixture project đại diện |
| Không theo dõi version consumer | Không biết ai còn dùng version lỗi thời | Adoption inventory và upgrade automation |

## 23. Checklist thiết kế pipeline dùng lại

Trước khi áp dụng cho nhiều dự án, hãy xác nhận:

- [ ] Đã xác định capability nào thật sự dùng chung.
- [ ] Phần riêng của dự án được biểu diễn bằng config rõ ràng.
- [ ] Đã chọn đúng mức tái sử dụng: template, workflow, action hoặc library.
- [ ] Input có kiểu, required/default, enum và validation.
- [ ] Output có cấu trúc, có schema và semantics rõ.
- [ ] Project config được validate trước khi thực thi.
- [ ] Precedence giữa organization, shared defaults, project và environment được xác định.
- [ ] Policy bắt buộc không thể bị project override.
- [ ] Profiles đại diện cho nhóm dự án ổn định.
- [ ] Extension point có giới hạn vị trí, quyền, timeout và output.
- [ ] Build/test được tách khỏi publish/deploy có quyền cao.
- [ ] Secret được lấy theo job và environment.
- [ ] Artifact dùng digest bất biến và có provenance phù hợp.
- [ ] Shared component, schema và profile được version hóa.
- [ ] Breaking change có migration guide và deprecation window.
- [ ] Có fixture project và contract/integration/security tests.
- [ ] Có adoption inventory, owner và quy trình nâng cấp.
- [ ] Log ghi shared workflow version và resolved config.
- [ ] Có cơ chế xử lý exception và policy override được phê duyệt.
- [ ] Có quy trình rollback shared workflow khi version mới gây lỗi.

## 24. Bài tập tự đánh giá

Một tổ chức có 40 repository: 18 Java service, 8 Java library, 10 frontend và 4 worker. Hiện mỗi repository có workflow riêng. Platform team muốn tạo một pipeline dùng chung duy nhất.

Yêu cầu của tổ chức:

- Mọi dự án phải có unit test và dependency scan.
- Service và worker cần integration test.
- Library cần publish package nhưng không deploy.
- Frontend cần build bundle và deploy lên CDN.
- Production deploy cần approval và identity riêng.
- Project team được khai báo build command và test profile.
- Không được cho project tắt policy security bắt buộc.
- Một số dự án cần custom smoke test sau deploy.

Hãy thiết kế:

1. Nên chia reusable workflow thành những capability nào?
2. Cần bao nhiêu profile và mỗi profile mô tả điều gì?
3. Input contract cần những trường nào?
4. Cấu hình nào được project override và cấu hình nào do organization policy kiểm soát?
5. Làm thế nào để library không gọi nhầm deployment workflow?
6. Custom smoke test nên chạy ở extension point nào và với quyền gì?
7. Artifact contract của Java package, container image và frontend bundle khác nhau ra sao?
8. Versioning và deprecation được quản lý thế nào?
9. Cần kiểm thử các fixture repository nào trước khi rollout?
10. Làm thế nào xác định repository nào chưa nâng cấp khỏi version cũ?

Một thiết kế tốt không ép cả 40 repository vào cùng một nhánh điều kiện phức tạp. Hãy dùng một contract nền tảng, một số workflow theo capability, profile theo loại dự án và cấu hình rõ ràng cho từng repository.

## Kết luận

Pipeline dùng lại giúp nhiều dự án chia sẻ quy trình, policy và cơ chế thu thập bằng chứng. Để tránh tạo ra một abstraction khó hiểu, cần phân biệt rõ phần bắt buộc dùng chung, khác biệt được cấu hình và extension point có kiểm soát.

Hãy thiết kế contract đầu vào/đầu ra có kiểu, validate cấu hình sớm, xác định precedence, tách quyền build khỏi publish/deploy và version hóa workflow cùng schema. Khi consumer biết chính xác họ đang gọi phiên bản nào, cung cấp input gì và nhận output nào, tổ chức có thể nâng cấp CI/CD tập trung mà vẫn giữ được khả năng cấu hình minh bạch cho từng dự án.

