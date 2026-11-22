# Phiên bản hóa cấu hình, kiểm soát sai lệch và quay lại bản đã biết trong Spring Boot

## 1. Tổng quan

Spring Boot hỗ trợ Externalized Configuration: giá trị ứng dụng có thể đến từ tệp YAML/properties, profile, biến môi trường, system properties, tham số dòng lệnh, Config Data import và nhiều PropertySource khác. Cách này cho phép dùng cùng một application artifact tại development, staging và production.

Tuy nhiên, việc cấu hình thay đổi độc lập với mã nguồn tạo ra những câu hỏi vận hành:

- Phiên bản cấu hình nào đã chạy khi sự cố xuất hiện?
- Một người sửa trực tiếp ConfigMap có làm production khác Git không?
- Nếu lệnh khởi động override timeout, file `application-prod.yml` còn phản ánh giá trị thực không?
- Khi một release gây lỗi, cần rollback application image, config hay cả hai?
- Một secret đã bị thu hồi có nên được khôi phục chỉ vì nằm trong bản release trước?

Ba năng lực cần xây dựng:

1. **Versioning:** cấu hình thay đổi có commit, review, version và artifact xác định.
2. **Drift control:** phát hiện trạng thái thực tế lệch khỏi trạng thái mong muốn hoặc khác biệt không được phê duyệt.
3. **Rollback:** khôi phục một tập app/config đã được kiểm chứng, không chỉ đổi một nhãn tên phiên bản.

Các năng lực này thuộc quy trình triển khai và vận hành. Spring Boot cung cấp cơ chế binding, precedence và validation, nhưng không tự xây hộ quy trình quản lý phiên bản và rollback đầy đủ.

## 2. Desired, deployed và effective configuration

Cần phân biệt:

| Khái niệm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| Desired | Cấu hình dự định, được phê duyệt | Git commit `abc123` có `timeout=5s` |
| Deployed | Cấu hình nền tảng đã cấp cho workload | ConfigMap `catalog-cfg-v17`, Secret reference |
| Effective | Giá trị Spring Boot thực sự chọn sau precedence/binding | `timeout=30s` do CLI override |

Ví dụ file production:

~~~yaml
app:
  catalog:
    timeout: 5s
~~~

Nhưng process chạy bằng:

~~~bash
java -jar catalog.jar --spring.profiles.active=prod --app.catalog.timeout=30s
~~~

Theo thứ tự ưu tiên cấu hình Spring Boot thông thường, command-line argument có thể thắng giá trị trong Config Data. File Git đúng không có nghĩa effective value đúng.

Muốn kiểm soát drift, hãy trả lời cả ba câu hỏi: Git muốn gì, nền tảng đã cấp gì, và chương trình đã bind gì. Không kiểm tra bằng cách chỉ đọc một tệp YAML.

## 3. Các định danh release cần lưu

Một bản release nên ghi tối thiểu:

- **Application version:** số phiên bản hoặc Git commit của ứng dụng.
- **Image digest/JAR checksum:** xác định artifact thực, tránh chỉ dựa vào floating tag.
- **Configuration Git commit:** trạng thái nguồn phi bí mật đã review.
- **Config artifact digest:** nội dung manifest/rendered values của môi trường.
- **Deployment ID:** pipeline run hoặc lần rollout.
- **Profile:** profile đang kích hoạt.
- **Secret reference/version:** định danh bí mật, không chứa plaintext.
- **Approval/verification evidence:** người duyệt, test và quan sát sau rollout.

Ví dụ minh họa:

~~~json
{
  "service": "catalog-api",
  "environment": "production",
  "appVersion": "2.4.1",
  "imageDigest": "sha256:<image-digest>",
  "configRevision": "cfg-17",
  "configGitCommit": "abc123def456",
  "deploymentId": "deploy-1842",
  "secretReference": "catalog-api/production",
  "secretVersion": "approved-current"
}
~~~

Một image có thể dùng nhiều config revision. Ngược lại, một config revision có thể chỉ hỗ trợ từ một app version nhất định. Không được dùng một trường `serviceVersion` để thay thế toàn bộ thông tin này.

## 4. Versioning bằng Git cho cấu hình phi bí mật

Những setting thích hợp với Git:

~~~yaml
app:
  catalog:
    connect-timeout: 3s
    read-timeout: 8s
    max-retries: 2
    enabled: true
~~~

Git giúp review diff, xác định tác giả, rollback bằng revert commit và so sánh giữa các môi trường.

Không commit secret thật:

~~~yaml
# Ví dụ không an toàn
spring:
  datasource:
    password: "REAL_PASSWORD"
~~~

Thay bằng một nguồn cấp bí mật phù hợp:

~~~yaml
spring:
  datasource:
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
~~~

Placeholder chỉ minh họa cách tham chiếu. Environment variables không phải secret store tuyệt đối; process inspection, crash dump hoặc log sai có thể làm lộ giá trị. Trong production, cân nhắc secret manager hoặc mounted secret file có phân quyền, rotation và audit.

Nếu credential từng được commit, xóa ở commit mới không có nghĩa nó biến mất khỏi Git history, clone hoặc backup. Cần đánh giá rủi ro và thu hồi/xoay vòng.

## 5. Repository cấu hình tham khảo

~~~text
deployment-config/
  README.md
  services/
    catalog-api/
      common/
        application.yml
      environments/
        dev/
          application-dev.yml
          deployment.yaml
        staging/
          application-staging.yml
          deployment.yaml
        production/
          application-prod.yml
          deployment.yaml
      schema/
        configuration-guide.md
      releases/
        release-2.4.1.json
  policies/
    reviewers.md
    release-checklist.md
    rollback-runbook.md
~~~

Đây là sơ đồ tổ chức tham khảo. Với Helm, Kustomize hoặc GitOps controller, tên thư mục có thể khác. Các tiêu chí quan trọng là:

1. Có nơi định nghĩa desired state theo môi trường.
2. Thay đổi có PR/review.
3. Không chứa secret plaintext.
4. Build/deploy pin exact commit.
5. Có artifact có thể truy xuất lại.
6. Có cách kiểm tra khác biệt giữa môi trường.
7. Có runbook rollback và người chịu trách nhiệm.

Nếu pipeline chỉ ghi “deploy branch main”, sau khi branch thay đổi sẽ không thể tái tạo chắc chắn đúng nội dung đã triển khai nếu không lưu commit SHA.

## 6. Cấu hình chung và cấu hình theo profile

Tệp `application.yml`:

~~~yaml
spring:
  application:
    name: catalog-api
app:
  catalog:
    connect-timeout: 3s
    read-timeout: 8s
    max-retries: 2
~~~

Tệp `application-prod.yml`:

~~~yaml
app:
  catalog:
    read-timeout: 5s
    max-retries: 3
~~~

Khi profile `prod` được kích hoạt, tài liệu cấu hình theo profile có thể override giá trị chung theo quy tắc Config Data. Nhưng giá trị cuối vẫn có thể bị override bởi environment, CLI, system properties hoặc imported configuration.

Vì vậy deployment record phải chỉ rõ profile, nguồn external config được phê duyệt và những override nào được phép.

Với collection như List, không suy diễn rằng nội dung từ hai nguồn sẽ được ghép từng phần tử. Spring Boot có quy tắc merge/replacement theo kiểu đích và property source. Nếu list là cấu hình quan trọng, phải kiểm tra kết quả binding thực tế.

## 7. Policy về nguồn cấu hình có quyền quyết định

Giả sử Git chứa:

~~~properties
app.catalog.max-retries=3
~~~

Environment:

~~~text
APP_CATALOG_MAXRETRIES=6
~~~

CLI:

~~~bash
java -jar catalog.jar --app.catalog.max-retries=1
~~~

Trong trường hợp thông dụng, giá trị cuối có thể là 1. Để tránh khó kiểm soát:

- Setting phi bí mật có một authoritative source.
- Secret có nguồn riêng và quy trình rotation.
- CLI/`-D` overrides chỉ dùng khi được phép.
- Override khẩn cấp phải có ticket, owner và hạn xử lý.
- Không để nhiều nhóm âm thầm điều chỉnh cùng property.
- Không log toàn bộ `Environment` để truy tìm override.
- Với production, dùng quan sát theo allowlist để biết những effective setting thiết yếu.

Không tự ghép các YAML files rồi coi đó là effective configuration; dùng quy tắc của Spring Boot và xác minh trên ứng dụng đúng version.

## 8. Digest và revision phải có ý nghĩa

Một field:

~~~yaml
app:
  config:
    revision: cfg-17
~~~

hữu ích để truy vết nhưng không chứng minh toàn bộ cấu hình đều thuộc `cfg-17`. Người vận hành có thể đổi timeout qua env trong khi revision giữ nguyên.

Một pipeline tốt hơn:

1. Checkout exact Git commit.
2. Render template/overlay.
3. Tạo config artifact phi bí mật bất biến.
4. Tính digest theo định dạng chuẩn hóa đã định nghĩa.
5. Lưu digest trong release record.
6. Đối chiếu live manifest với artifact khi deploy.
7. Xác minh một số effective setting sau bind.

Phân biệt:

| Fingerprint | Bao phủ | Giới hạn |
| --- | --- | --- |
| Raw-file SHA-256 | Byte của tệp | Comment/whitespace cũng đổi hash |
| Rendered-manifest SHA-256 | Artifact manifest đã render | Chưa chắc bao phủ runtime overrides |
| Allowlisted effective settings | Một nhóm property được phép quan sát | Không bao phủ mọi property |
| Secret version ID | Phiên bản credential | Không công khai nội dung secret |

Không log hash thô của password entropy thấp: hash có thể hỗ trợ kẻ khác đoán giá trị. Với credential, lưu reference/version do secret manager cấp và kiểm soát quyền xem.

## 9. Release metadata trong Kubernetes

Có thể gắn revision được pipeline phê duyệt vào Pod template:

~~~yaml
spec:
  template:
    metadata:
      annotations:
        example.org/config-revision: "cfg-17"
        example.org/config-commit: "abc123def456"
~~~

Annotation ở namespace `example.org` chỉ là ví dụ do đội vận hành tự đặt. Kubernetes không tự xác minh rằng label này khớp nội dung ConfigMap. Hệ thống phát hành phải ràng buộc nó với artifact.

Thay đổi Pod template có thể tạo revision mới của Deployment và kích hoạt rollout. Tuy nhiên, annotation không bảo đảm application image, secret và ConfigMap đúng chỉ nhờ có một chuỗi version.

Với mỗi lần triển khai, lưu liên kết từ deployment ID đến image digest, config commit, rendered manifest và test evidence.

## 10. Schema cấu hình có kiểu và validation

Một class có kiểu rõ ràng giúp phát hiện lỗi trong các revision.

~~~java
package com.example.catalog.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        @NotBlank String baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(0) @Max(10) int maxRetries
) {}
~~~

Đăng ký:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {}
~~~

Trong Spring Boot 3.x, Bean Validation cần provider phù hợp, thường được cấp qua `spring-boot-starter-validation`. Record có constructor phù hợp có thể được constructor-bound khi bean được đăng ký bằng cơ chế configuration properties.

Giới hạn cần hiểu:

- `@NotBlank` không xác minh URL có scheme/host hợp lệ.
- `@NotNull Duration` không tự yêu cầu thời lượng lớn hơn 0.
- Primitive `int` có thể nhận giá trị 0 khi thiếu field.
- Value sai kiểu có thể gây lỗi conversion trước validation.
- Validator không thay smoke test khả năng kết nối thực tế.

Tuy nhiên, schema và validation giúp giảm rủi ro deploy một revision chứa giá trị hiển nhiên không hợp lệ.

## 11. Pipeline phải kiểm tra nhiều lớp

| Tầng | Ví dụ | Cơ chế |
| --- | --- | --- |
| Syntax | YAML indentation sai | YAML parser/linter |
| Tên property | `max-retrie` bị gõ sai | Schema và strict unknown-field check |
| Type conversion | `timeout=tomorrow` | Spring Binder |
| Constraint | `max-retries=-5` | Bean Validation |
| Cross-field | Enabled nhưng thiếu endpoint | Class-level validator/constructor invariant |
| App/config compatibility | App cũ không hiểu key mới | Ma trận phiên bản và integration test |
| Secret reference | Secret key không tồn tại | Kiểm tra deploy-time được cấp quyền |
| Behavior | Upstream chậm/lỗi | Smoke và operational metrics |

Với `@ConfigurationProperties`, có thể cân nhắc `ignoreUnknownFields=false` để phát hiện property không bind được trong namespace do một class sở hữu. Không nên bật một chính sách strict quá rộng trên namespace nhiều module chia sẻ mà không có schema đầy đủ.

Một YAML file hợp lệ về cú pháp chưa chắc là cấu hình chạy được.

## 12. Pull request cấu hình nên có gì?

Một diff:

~~~diff
 app:
   catalog:
-    read-timeout: 8s
+    read-timeout: 5s
~~~

PR nên mô tả:

- Lý do thay đổi.
- Phạm vi môi trường/service.
- App versions tương thích.
- Rủi ro với latency, timeout, retry hoặc resource.
- Các test đã chạy.
- Metric thành công và ngưỡng rollback.
- Revision known good.
- Người review và phê duyệt.

Một thay đổi một dòng YAML vẫn có thể làm toàn bộ dịch vụ lỗi; số dòng của diff không phản ánh mức độ rủi ro. Những setting như timeout, feature flag, retry budget hoặc connection pool cần chính sách release phù hợp.

## 13. Promotion qua các môi trường

~~~text
Pull request
      |
      v
Lint + schema + policy
      |
      v
Approved commit and config artifact
      |
      v
Development deployment
      |
      v
Staging integration/smoke tests
      |
      v
Production approval
      |
      v
Canary or staged rollout
      |
      v
Verify SLO and effective config
      |
      +--- failure ---> rollback
      |
      v
Mark revision known good
~~~

Không nhất thiết staging và production có cùng mọi giá trị. Endpoint và secret phải khác nhau, một số limits cũng khác có chủ đích. Nhưng hai môi trường nên được tạo từ nguồn revision và quy tắc render đã duyệt.

Tránh việc thử trên staging từ một commit, rồi chỉnh tay một file khác để deploy production mà không review/test lại.

## 14. Configuration drift là gì?

Drift là sai lệch ngoài chủ đích giữa desired state và trạng thái thực tế.

Có nhiều dạng:

1. **Source drift:** file trên máy chủ bị sửa, Git không đổi.
2. **Deployment drift:** manifest live khác rendered manifest đã phê duyệt.
3. **Effective drift:** env/CLI/system property override ngoài kế hoạch.
4. **Pod drift:** Pod trong cùng service đang dùng những image/config revision khác nhau ngoài mong muốn.
5. **Secret-reference drift:** workload dùng sai secret path hoặc phiên bản.
6. **Environment drift:** staging và production khác ngoài baseline.
7. **Schema drift:** code đổi tên/loại field nhưng config chưa cập nhật.
8. **Emergency drift:** hotfix trực tiếp trong cluster không được đồng bộ về Git.

Không phải khác biệt nào cũng xấu. Staging dùng timeout 8s còn production 5s có thể hoàn toàn đúng, nếu được review và lưu trong environment-specific baseline.

## 15. So sánh desired với live state

~~~text
Git approved config
        |
        v
Render manifest
        |
        +-------------------+
        |                   |
        v                   v
Expected snapshot     Live deployment snapshot
        |                   |
        +---------+---------+
                  |
                  v
          Compare allowlisted fields
                  |
         +--------+--------+
         |                 |
         v                 v
     No drift          Drift detected
                           |
                           v
                    Alert / investigate
~~~

Nên so:

- Image digest.
- ConfigMap name/revision/digest.
- Pod template annotations.
- Profile/allowed environment settings.
- Một số field phi bí mật có giá trị vận hành.
- Secret reference/version, không phải secret plaintext.
- Deployment revision và thời điểm.

Không dump toàn bộ `Environment` qua network để so; việc đó có thể xuất password, token, certificate hoặc connection string. Những property source không hỗ trợ enumeration đầy đủ cũng có thể khiến công cụ không nhìn thấy mọi setting; cần nêu rõ phạm vi kiểm tra.

## 16. Phát hiện và xử lý manual drift

Ví dụ người vận hành sửa trực tiếp:

~~~bash
kubectl edit configmap catalog-config -n production
~~~

Điều này có thể làm live state lệch Git. Trong hệ thống GitOps, controller có thể reconcile thay đổi; nếu không có controller, drift có thể tồn tại tới lần deployment sau.

Chính sách:

- Giới hạn RBAC sửa trực tiếp tài nguyên production.
- Thay đổi thường lệ đi qua repository và pipeline.
- Emergency hotfix phải có ticket, lý do, người thực hiện và thời hạn.
- Đưa hotfix về Git hoặc loại bỏ sau xử lý.
- Theo dõi audit log và drift alert.
- Không coi GitOps “Synced” là bằng chứng effective value đúng nếu Spring Boot còn nguồn override khác.

Với sự cố, manual override có thể cần thiết, nhưng không được trở thành nguồn cấu hình vô hình.

## 17. Kubernetes ConfigMap với version

Ví dụ ConfigMap phi bí mật:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-config-v17
  namespace: production
  labels:
    app: catalog-api
    example.org/config-revision: "cfg-17"
data:
  APP_CATALOG_CONNECTTIMEOUT: "3s"
  APP_CATALOG_READTIMEOUT: "5s"
  APP_CATALOG_MAXRETRIES: "3"
~~~

Các biến trên áp dụng dạng tên canonical Spring Boot: dấu chấm thành `_`, bỏ gạch ngang và uppercase.

Deployment có thể dùng:

~~~yaml
envFrom:
  - configMapRef:
      name: catalog-config-v17
~~~

Với `envFrom`, environment được cấp khi container bắt đầu. **Sửa ConfigMap sau đó không tự thay đổi environment của một process đang chạy.**

ConfigMap không dành cho secret. Kubernetes Secret cũng không tự có mã hóa bảo mật chỉ vì giá trị `data` được viết Base64; cần RBAC, bảo vệ etcd, Pod permissions và secret rotation.

## 18. Volume config và Spring Boot reload

Kubernetes có thể mount ConfigMap/Secret thành file. File volume thông thường có thể nhận cập nhật sau một độ trễ; mount qua `subPath` có những giới hạn cập nhật khác.

Spring Boot có thể nạp config tree:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
~~~

Nhưng **thay file sau startup không mặc nhiên làm mọi `@ConfigurationProperties` bean bind lại**. Nếu dự án không thiết kế refresh mechanism, cách dễ kiểm soát là:

1. Tạo config revision mới.
2. Cập nhật Deployment/Pod template.
3. Rollout các Pod mới.
4. Xác nhận readiness và smoke test.
5. Kiểm tra revision và effective values được phép quan sát.

Giải pháp dynamic refresh cần cơ chế riêng, có test consistency và audit thời điểm áp dụng.

## 19. Versioned ConfigMap và immutable resource

Thay vì sửa một ConfigMap mutable:

~~~text
catalog-config
~~~

có thể phát hành:

~~~text
catalog-config-v16
catalog-config-v17
catalog-config-v18
~~~

Ưu điểm: Pod template tham chiếu phiên bản cụ thể, giảm thay đổi ngầm, có thể giữ resource cũ cho rollback.

Nhưng phải:

- Duy trì resource cũ trong rollback window.
- Không tin tên `v17` mà bỏ qua content digest.
- Có policy cleanup/retention.
- Kiểm soát những override bên ngoài ConfigMap.
- Không tạo các resource mới chỉ để che lỗi quản lý state.

Kubernetes có tùy chọn `immutable` cho ConfigMap/Secret trong trường hợp phù hợp. Khi cần sửa nội dung một object immutable, thường phải tạo object mới rồi đổi reference, không update phần data cũ.

## 20. Kích hoạt rollout bằng annotation

Ví dụ Pod template:

~~~yaml
spec:
  template:
    metadata:
      annotations:
        example.org/config-digest: "<approved-config-artifact-digest>"
~~~

Pipeline tính digest và cập nhật nó cùng config revision. Đổi Pod template có thể tạo ReplicaSet mới.

Tuy nhiên, **annotation không giữ ConfigMap cùng tên bất biến**. Nếu ConfigMap bị sửa nhưng annotation vẫn nói `cfg-17`, một Pod mới có thể nạp dữ liệu không còn thuộc revision đó.

Với hệ thống yêu cầu tái lập và rollback nghiêm ngặt, versioned resource hoặc một artifact được khóa nội dung là lựa chọn rõ ràng hơn.

## 21. Rollout success chưa có nghĩa ứng dụng dùng đúng config

Lệnh:

~~~bash
kubectl rollout status deployment/catalog-api -n production
~~~

giúp xem Deployment rollout tiến đến trạng thái mong muốn, nhưng không chứng minh:

- `spring.profiles.active` đúng.
- Một environment variable không override timeout.
- Secret reference đúng version.
- Bean validation đạt mọi quy tắc nghiệp vụ.
- Remote API còn hoạt động.
- Error rate/latency đáp ứng mục tiêu.

Do đó cần kiểm tra Pod image/config reference, startup/validation, smoke test và operational metrics. Readiness chỉ là một tín hiệu trong bộ bằng chứng release.

## 22. Quan sát cấu hình không làm lộ secret

Spring Boot Actuator có `env` và `configprops`, hữu ích cho chẩn đoán. Tuy nhiên, không mở công khai chỉ để xem drift.

Ví dụ cấu hình hạn chế:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Nếu cần endpoint diagnostic riêng, chỉ trả những field được allowlist và bảo vệ quyền truy cập:

~~~json
{
  "service": "catalog-api",
  "applicationVersion": "2.4.1",
  "configRevision": "cfg-17",
  "profile": "prod",
  "settings": {
    "connectTimeoutSeconds": 3,
    "readTimeoutSeconds": 5,
    "maxRetries": 3
  }
}
~~~

Không trả whole configuration bean chứa `apiKey`, không log `toString()` của Java record có credential. Một trường version do app tự báo chỉ là metadata, không tự chứng minh không có override khác.

## 23. Khác biệt giữa các môi trường

Ví dụ:

| Thuộc tính | Staging | Production | Được duyệt? |
| --- | --- | --- | --- |
| `connect-timeout` | 3s | 3s | Đồng nhất |
| `read-timeout` | 8s | 5s | Có |
| `max-retries` | 2 | 3 | Có |
| `feature-x-enabled` | true | false | Có, staged rollout |
| `unknown-flag` | true | true | Cần xem schema |

Một baseline có thể ghi:

~~~yaml
allowed-differences:
  app.catalog.read-timeout:
    staging: 8s
    production: 5s
    reason: "Production latency target"
  app.catalog.max-retries:
    staging: 2
    production: 3
    reason: "Approved retry policy"
~~~

Không so secret thô giữa môi trường; production/staging cần credentials tách biệt. Drift detection phải phân biệt khác biệt **chủ đích** với khác biệt **không được phê duyệt**.

## 24. “Known good” cần bằng chứng

Một tag `stable` không tự động là bản known good.

Các điều kiện thường dùng:

- Cấu hình đúng syntax/schema.
- App artifact/config revision tương thích.
- Secret reference hợp lệ.
- Bean Validation và startup thành công.
- Rollout/readiness đạt.
- Smoke test đạt.
- Error rate, latency, timeout, saturation trong ngưỡng.
- Không có drift chưa giải thích.
- Có timestamp, approver và artifact ID đầy đủ.

Một bản đã pass staging không mặc nhiên là known good production nếu traffic, upstream hoặc secret khác. Release record nên gắn chứng cứ với môi trường thực tế.

## 25. Rollback gì khi cấu hình gây sự cố?

| Tình huống | Cách xử lý |
| --- | --- |
| Timeout tăng quá cao | Quay về config revision phù hợp |
| App mới đòi field config chưa có | Bổ sung config hoặc quay app/config về cặp tương thích |
| Secret mới có quyền sai | Sửa secret reference/permission, không tự phục hồi secret yếu |
| ConfigMap đổi nhưng Pod chưa restart | Rollout Pod dùng revision đúng |
| Cấu hình cũ không tương thích DB migration | Kế hoạch migration/khôi phục riêng |
| Feature flag thay động | Rollback trong provider flag, kiểm tra propagation |

Rollback là **một lần triển khai được kiểm soát**, không đơn giản copy lại file YAML cũ. Cần biết cả app version, config revision, secret version và hạ tầng liên quan.

## 26. Runbook rollback

### Bước 1 — Ghi hiện trạng

~~~text
Service: catalog-api
Current deployment: deploy-1842
Current configuration: cfg-18
Last known good: deploy-1837 / cfg-17
Symptom: timeout rate exceeds threshold
~~~

Đây là ID minh họa.

### Bước 2 — Điều tra phạm vi

So sánh thay đổi code, config, traffic, secret, database và upstream. Không suy ra nguyên nhân chỉ vì sự cố xuất hiện sau một commit.

### Bước 3 — Xác minh bản cũ còn dùng được

Kiểm tra app/config compatibility, database migration và secret references; credential đã bị revoke vì compromise không được khôi phục.

### Bước 4 — Đảo thay đổi

Có thể tạo Git revert commit hoặc triển khai lại artifact bất biến đã được lưu. Không sửa tạm trong container rồi gọi đó là rollback hoàn tất.

### Bước 5 — Rollout và đối chiếu

Xác nhận Pod template, ConfigMap/Secret references, profile, image digest và các effective property phi bí mật.

### Bước 6 — Kiểm tra dịch vụ

Chờ readiness, chạy smoke test, xem error rate/latency/timeout/saturation và phát hiện drift còn lại.

### Bước 7 — Audit

Ghi deployment ID mới, các bước thực thi, người phê duyệt, kết quả và biện pháp phòng ngừa. Không xóa lịch sử release thất bại.

## 27. Git revert khác checkout

Một thay đổi:

~~~diff
-app.catalog.read-timeout=5s
+app.catalog.read-timeout=45s
~~~

Có thể đảo bằng:

~~~bash
git revert <bad-config-commit>
~~~

Revert tạo commit mới, giúp giữ audit trail. Nếu commit chứa nhiều thay đổi hợp lệ khác, có thể tạo PR đảo chính xác các field cần khôi phục.

Trong khi đó:

~~~bash
git checkout <known-good-commit>
~~~

chỉ đổi working tree của checkout, **không tự thay production**. Vẫn cần render, test, approve, deploy và verify.

Trong GitOps, bản sửa/revert trong Git thường bền vững hơn một hotfix trực tiếp, nhưng cần runbook khẩn cấp khi hệ thống GitOps không sẵn sàng.

## 28. Giới hạn của Kubernetes rollout undo

Lệnh:

~~~bash
kubectl rollout undo deployment/catalog-api -n production
~~~

nhắm tới lịch sử Pod template revision của Deployment. Nó **không tự khôi phục nội dung ConfigMap, Secret, external config service hoặc database**.

Ví dụ:

1. Pod template tham chiếu ConfigMap cùng tên `catalog-config`.
2. Người vận hành sửa ConfigMap từ 5s thành 45s.
3. Pod mới dùng 45s.
4. `rollout undo` quay Pod template, nhưng ConfigMap vẫn chứa 45s.

Khi Pod chạy lại, nó có thể tiếp tục nhận 45s.

Versioned ConfigMap như `catalog-config-v17` giúp Pod template có thể quay về reference cũ **nếu resource vẫn còn và những override khác phù hợp**. Luôn xác minh cả reference, nội dung resource và giá trị hiệu lực.

## 29. Không khôi phục secret đã bị thu hồi

Một token cũ đã bị lộ và revoked có thể nằm trong bản known good trước đây. Quay lại đúng snapshot cũ có thể làm ứng dụng thất bại hoặc khôi phục một cơ chế bảo mật yếu.

Cần:

- Tách rollback của setting phi bí mật và credential.
- Kiểm tra secret reference/version còn hợp lệ.
- Giữ những security remediation đã được áp dụng.
- Nếu app cũ không hỗ trợ phương thức auth mới, triển khai compatibility fix thay vì quay lại credential đã compromise.
- Ghi audit của thay đổi secret mà không xuất giá trị.

**Rollback vận hành không được vô tình đảo một quyết định thu hồi credential vì bảo mật.**

## 30. Database schema và feature flags

Một setting:

~~~yaml
app:
  features:
    new-order-schema: true
~~~

có thể yêu cầu database schema mới. Nếu dữ liệu đã được migrate không tương thích ngược, chỉ đảo flag chưa chắc khôi phục được hành vi cũ. Khi cần cửa sổ rollback, thiết kế migration theo hướng expand–migrate–contract phù hợp.

Feature flags động có thể thay đổi ngoài Git. Khi đó phải lưu lịch sử provider, targeting, cache/polling và thời điểm hiệu lực. Git config commit chỉ mô tả một phần state.

Không giả định Spring Boot sẽ tự bind lại mọi `@ConfigurationProperties` bean khi file nguồn thay đổi. Nếu có refresh mechanism riêng, phải thiết kế test và audit dành riêng cho nó.

## 31. Canary cho config revision

~~~text
Approve cfg-18
       |
       v
Deploy to a limited canary
       |
       v
Observe latency, errors, retry, saturation
       |
       +--- failure ---> restore cfg-17
       |
       v
Promote progressively
       |
       v
Verify full production and mark known good
~~~

Nên định nghĩa trước:

- Phần trăm traffic hoặc Pod thử nghiệm.
- Chỉ số so sánh và ngưỡng fail.
- Thời gian quan sát phù hợp traffic.
- Người quyết định dừng/rollback.
- Cách phân biệt Pod cfg-17/cfg-18.
- Cách khôi phục config artifact đúng nếu thất bại.

Nếu các Pod dùng chung ConfigMap mutable và giá trị thay đổi không kiểm soát, canary có thể không còn phản ánh một snapshot nhất quán.

## 32. Ma trận app/config compatibility

Ví dụ:

| Application | cfg-16 | cfg-17 | cfg-18 |
| --- | --- | --- | --- |
| 2.3.x | Đã kiểm chứng | Cần regression test | Không hiểu field mới |
| 2.4.0 | Có fallback | Đã kiểm chứng | Đạt staging |
| 2.4.1 | Có fallback | Known good production | Đang canary |

Đây là bảng mẫu. Khi quay app 2.4.1 về 2.3.x, cfg-18 có thể không còn tương thích. Cần chọn **cặp app/config** đã được kiểm chứng.

Một config schema version có thể giúp pipeline nhận diện compatibility, nhưng chỉ có ý nghĩa nếu CI hoặc startup kiểm tra thực tế.

Thay tên property từ `retry-count` sang `max-retries` cần migration plan, deprecation window hoặc backward-compatible binding nếu muốn rolling upgrade. Metadata phục vụ IDE không tự chuyển mọi tên cũ sang tên mới tại runtime.

## 33. Test cấu hình bằng Spring Boot Test

Một kiểm thử bằng `ApplicationContextRunner`:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogConfigurationTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void approvedConfigurationCanBind() {
        runner.withPropertyValues(
                "app.catalog.base-url=https://catalog.example.org",
                "app.catalog.connect-timeout=3s",
                "app.catalog.read-timeout=5s",
                "app.catalog.max-retries=3"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            CatalogProperties props =
                    context.getBean(CatalogProperties.class);
            assertThat(props.readTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
    }
}
~~~

Ví dụ giả định class ở phần 10 và dependency Spring Boot Test/JUnit/AssertJ/validation thích hợp. Thêm test `max-retries=99` và kiểm tra context thất bại vì constraint phù hợp.

Trong CI thực tế, tốt nhất kiểm tra trên **config artifact/overlay định triển khai**, không chỉ literal trong test không gắn với trạng thái production.

## 34. Pipeline kiểm soát cấu hình

Một quy trình CI/CD:

~~~text
1. Checkout pinned application and config commits
2. Validate YAML/JSON syntax
3. Render environment overlays
4. Scan for plaintext secrets/policy violations
5. Validate schema and required fields
6. Run Binder + Bean Validation tests
7. Check application/config compatibility
8. Produce immutable non-secret config artifact
9. Save digest, approvals and deployment metadata
10. Deploy staging and run smoke/integration tests
11. Approve production
12. Canary/staged rollout
13. Observe metrics and compare revision
14. Mark known good or rollback
~~~

Dự án có thể dùng GitHub Actions, GitLab CI, Jenkins, Argo CD, Flux hoặc nền tảng riêng. Tool không quan trọng bằng việc artifact có thể tái hiện và đủ bằng chứng.

Pipeline không nên lưu secret đã giải mã trong artifact/log. Test PR có thể dùng credential giả, còn deploy-time kiểm tra secret reference qua quyền truy cập giới hạn.

## 35. Promotion từ immutable artifact

Anti-pattern:

~~~text
Staging: render branch main on Monday
Production: render branch main on Thursday
~~~

Nếu branch đổi, production không chạy đúng cấu hình đã qua staging.

Pattern tốt hơn:

~~~text
Approved commit
       |
       v
Render exact artifact / environment overlay
       |
       v
Store immutable artifact + digest
       |
       +--> staging
       |
       +--> production
~~~

Giá trị endpoint/secret của hai môi trường có thể khác. Điều cần cố định là revision nguồn, logic render và các khác biệt môi trường đã được duyệt. Lưu digest theo từng artifact đã render.

## 36. Log revision, không log secret

Không làm:

~~~java
log.info("Environment: {}", environment);
log.info("Config bean: {}", credentials);
~~~

Một Java record có `toString()` mặc định có thể in token/password.

Có thể log metadata:

~~~java
log.info(
        "Release appVersion={} configRevision={} deploymentId={}",
        appVersion,
        configRevision,
        deploymentId
);
~~~

Nếu log các giá trị hiệu lực, chỉ dùng field phi bí mật đã được duyệt:

~~~java
log.info(
        "Catalog readTimeoutSeconds={} maxRetries={}",
        catalogProperties.readTimeout().toSeconds(),
        catalogProperties.maxRetries()
);
~~~

Không dùng hash của secret thô để so drift. Nếu cần xác định credential nào đã dùng, log reference/version đã được phép quan sát.

## 37. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Git đúng nhưng runtime sai | Env/CLI override | Tra nguồn effective |
| ConfigMap đổi nhưng Pod cũ không đổi | Environment nạp lúc startup | Rollout Pod mới |
| File mount thay mà bean giữ giá trị | Thiếu refresh mechanism | Restart hoặc cơ chế refresh riêng |
| Rollout undo nhưng timeout vẫn sai | ConfigMap mutable chưa revert | Khôi phục đúng resource/reference |
| Không biết cấu hình đang chạy bản nào | Không pin commit/digest | Release record bất biến |
| Staging pass, production fail | Overlay/secret/traffic khác | Kiểm thử baseline |
| Schema hợp lệ, app vẫn fail | Binding/validation/compatibility | Test app-config pair |
| Drift alert sai | Không lọc field động/khác biệt chủ đích | Allowlist và baseline |
| Hotfix tay tồn tại mãi | Thiếu reconcile/audit | GitOps/change control |
| Rollback gây lỗi auth | Secret cũ đã revoked | Dùng credential hiện tại hợp lệ |
| Rollback app lỗi database | Migration không tương thích | Expand–contract/recovery |
| Label revision đúng nhưng nội dung sai | Label không gắn với artifact | Digest và verification |
| Kiểm tra drift làm lộ password | Dump configuration bean | Diagnostic allowlist |

## 38. Bài tập tự kiểm tra

### Bài 1

Git `application-prod.yml` đặt timeout 5s, CLI đặt 20s. Có được kết luận ứng dụng dùng 5s không?

**Đáp án:** không. CLI có thể override Config Data. Phải xem effective property.

### Bài 2

Hai Pod có cùng image digest, nhưng một Pod dùng cfg-17 và Pod kia cfg-18. Chúng có hoàn toàn cùng bản vận hành không?

**Đáp án:** không. Cấu hình có thể thay hành vi dù binary giống nhau.

### Bài 3

Một password đã commit vào Git rồi bị xóa ở commit tiếp theo. Có đủ không?

**Đáp án:** không. Phải đánh giá phạm vi lộ và thu hồi/rotation vì Git history/clone/backup có thể còn giá trị.

### Bài 4

Deployment dùng envFrom ConfigMap. Sửa ConfigMap có tự cập nhật process đang chạy không?

**Đáp án:** không. Thường cần Pod mới để lấy environment đã đổi.

### Bài 5

`kubectl rollout undo` có tự restore nội dung ConfigMap cùng tên đã bị sửa không?

**Đáp án:** không. Nó chủ yếu khôi phục Pod template revision.

### Bài 6

Git tag tên stable chưa từng chạy production. Nó có mặc nhiên là production known good không?

**Đáp án:** không. Cần bằng chứng deploy và sức khỏe vận hành.

### Bài 7

Git muốn retries=3 nhưng CLI đặt retries=8. Đây là drift gì?

**Đáp án:** effective/runtime drift do override ngoài desired source.

### Bài 8

Có nên log SHA-256 của password để kiểm tra phiên bản secret không?

**Đáp án:** không nên mặc định. Hash của secret yếu có thể bị đoán; dùng version/reference ID.

### Bài 9

App 2.3 không hỗ trợ cfg-18, app 2.4 có hỗ trợ. Rollback app xuống 2.3 nhưng giữ cfg-18 có an toàn không?

**Đáp án:** chỉ khi đã kiểm chứng tương thích. Nên chọn cặp app/config known good.

### Bài 10

Staging timeout 8s, production 5s có bắt buộc là drift không?

**Đáp án:** không, nếu khác biệt được duyệt và ghi baseline.

### Bài 11

Secret cũ bị revoke vì compromise, bản known good trước dùng secret đó. Có được phục hồi không?

**Đáp án:** không. Giữ security remediation và dùng credential hợp lệ mới.

### Bài 12

Canary cfg-18 làm timeout rate tăng. Nêu bước xử lý.

**Đáp án gợi ý:** dừng promotion; xác định current/known-good revisions; kiểm tra compatibility và secret; khôi phục artifact cấu hình đúng; rollout; kiểm tra effective state, smoke và metrics; ghi incident.

## 39. Checklist triển khai

### Trước thay đổi

- [ ] Cấu hình phi bí mật được version hóa.
- [ ] Secret không nằm trong repository/artifact.
- [ ] Owner/reviewer được chỉ định.
- [ ] PR có mục đích, rủi ro và rollback trigger.
- [ ] Schema, validation và compatible app versions rõ ràng.
- [ ] Quy tắc override được giới hạn.
- [ ] Các khác biệt môi trường có baseline.

### Trước production

- [ ] Pin application image digest.
- [ ] Pin configuration commit/artifact digest.
- [ ] Render đúng overlay production.
- [ ] Xác nhận secret references mà không in giá trị.
- [ ] CI kiểm tra syntax, binding, constraints và compatibility.
- [ ] Staging/canary đã qua test.
- [ ] Có known-good release còn dùng được.
- [ ] Có approval và ngưỡng rollback.

### Sau deployment

- [ ] Xác nhận image và config references của Pod.
- [ ] Xác nhận readiness/smoke tests.
- [ ] Kiểm tra allowed effective values.
- [ ] Quan sát error, timeout, latency và resource saturation.
- [ ] Phát hiện drift giữa desired/deployed.
- [ ] Ghi deployment record và evidence.
- [ ] Kết thúc hoặc đồng bộ emergency overrides.

### Khi rollback

- [ ] Chọn cặp app/config tương thích đã kiểm chứng.
- [ ] Không hồi sinh secret bị thu hồi vì bảo mật.
- [ ] Khôi phục đúng ConfigMap/Pod template, không chỉ rollout undo.
- [ ] Khởi động Pod mới nếu cấu hình nạp lúc startup.
- [ ] Smoke test và xác nhận metrics.
- [ ] Ghi incident, người phê duyệt và hành động phòng ngừa.

## 40. Ghi nhớ

- **Versioning:** tách application artifact, config revision, deployment run và secret version.
- **Drift:** khác biệt ngoài chủ đích giữa desired, deployed và effective state.
- **Spring Boot precedence:** file Git có thể không quyết định giá trị cuối nếu env/CLI hoặc nguồn khác override.
- **ConfigMap env:** process không tự nhận giá trị mới sau khi ConfigMap đổi.
- **Mounted file:** thay file không đồng nghĩa mọi Spring Boot bean tự rebind.
- **Versioned resource:** giúp rollback dễ tái lập hơn một resource mutable cùng tên.
- **Rollout undo:** không khôi phục các ConfigMap/Secret độc lập.
- **Known good:** phải có evidence, không chỉ tag stable.
- **Rollback:** là một deployment mới, cần kiểm tra app/config/schema/secret compatibility.
- **Security:** không rollback credential bị compromise và không log secret để so drift.
- **Canary/staged rollout:** cho phép phát hiện rủi ro trước khi ảnh hưởng toàn bộ production.
- **Allowlist diagnostics:** quan sát những setting an toàn, không dump toàn bộ Environment.
- **Governance:** review, promotion, audit và drift detection quan trọng hơn manual override không lưu vết.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Config Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [OWASP — Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
