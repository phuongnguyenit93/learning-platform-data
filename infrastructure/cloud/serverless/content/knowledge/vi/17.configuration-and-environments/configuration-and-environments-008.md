# Đặt tên tài nguyên, gắn nhãn và truy nguyên nguồn triển khai

Một ứng dụng serverless có thể tạo ra nhiều tài nguyên: function, service HTTP, queue, topic, workflow, bucket, database, service account, revision và các cấu hình triển khai. Khi số lượng tài nguyên tăng, tên gọi tùy tiện khiến việc tìm kiếm, phân quyền, phân bổ chi phí và xử lý sự cố trở nên khó khăn.

Một quy ước tốt cần trả lời ba câu hỏi:

1. **Tài nguyên này là gì và thuộc hệ thống nào?** Tên tài nguyên cần ngắn, ổn định và dễ nhận diện.
2. **Tài nguyên thuộc môi trường, nhóm hoặc mục đích nào?** Labels, tags và annotations cung cấp metadata để lọc, quản trị và phân bổ chi phí.
3. **Tài nguyên đang chạy từ mã nguồn và bản build nào?** Provenance liên kết source commit, build, artifact, cấu hình và lần triển khai cụ thể.

Với Java serverless, cần áp dụng quy ước nhất quán cho cả tài nguyên cloud và metadata của ứng dụng. Khi một invocation lỗi, đội vận hành cần lần được từ log và execution ID đến function/service, revision, image digest, build và commit đã tạo ra artifact đó.

## 1. Phân biệt tên, label, tag và annotation

Các khái niệm này liên quan nhưng không thay thế cho nhau.

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Resource name | Định danh tài nguyên trong API hoặc nền tảng | orders-api-prod |
| Label | Metadata có cấu trúc để phân loại, lọc hoặc chọn tài nguyên | environment=production |
| Tag | Metadata gắn với tài nguyên cloud; thường dùng cho phân loại, policy hoặc cost allocation | team=commerce-platform |
| Annotation | Metadata bổ sung, thường dành cho công cụ hoặc thông tin vận hành | git commit, build URL |
| Runtime attribute | Metadata gắn với process/service đang chạy để log, metric và trace | service.version=2.4.1 |
| Release provenance | Bằng chứng liên kết source, build, artifact và deployment | commit SHA + image digest + release ID |

Tên tài nguyên thường là một phần của định danh hoặc URL và có giới hạn riêng. Label/tag thường có thể thay đổi mà không đổi danh tính tài nguyên. Annotation thường lưu thông tin chi tiết hơn, nhưng không nhất thiết được dùng làm selector hoặc filter ở mọi nền tảng.

Ví dụ trong Kubernetes, labels có thể được dùng trong selector để tìm Pod thuộc một Service hoặc Deployment. Annotations chứa metadata bổ sung và không được dùng cho selector chuẩn. Trên các cloud provider, tên gọi và khả năng của tags/labels khác nhau theo dịch vụ.

Không nên chọn một thuật ngữ rồi giả định mọi nền tảng thực hiện giống nhau. Hãy phân biệt mục đích và kiểm tra schema, giới hạn cùng khả năng lọc của dịch vụ đang dùng.

## 2. Xây dựng quy ước đặt tên tài nguyên

Một quy ước phổ biến là ghép các thành phần có ý nghĩa ổn định:

~~~text
<organization>-<system>-<component>-<environment>-<region>
~~~

Ví dụ:

~~~text
acme-orders-api-prod-asia-southeast1
acme-orders-worker-prod-asia-southeast1
acme-orders-events-prod-asia-southeast1
acme-orders-reconcile-job-prod-asia-southeast1
~~~

Không phải tài nguyên nào cũng cần đủ các thành phần. Nếu project/account hoặc namespace đã đại diện cho môi trường và region, tên có thể ngắn hơn:

~~~text
orders-api
orders-worker
orders-events
orders-reconcile
~~~

Mục tiêu là giúp người vận hành nhận ra tài nguyên mà không cần đoán. Tránh nhồi toàn bộ thông tin quản trị vào tên; labels/tags phù hợp hơn cho owner, cost center, data classification và tool quản lý.

### 2.1. Quy tắc thực tế

- Dùng chữ thường và dấu gạch ngang cho tên cần tính di động giữa nhiều nền tảng.
- Dùng từ viết tắt có danh mục thống nhất; không tự tạo nhiều biến thể cho cùng một khái niệm.
- Giữ tên ngắn, tránh nhúng mô tả dài hoặc câu tự do.
- Không đưa password, token, email cá nhân, customer ID hoặc dữ liệu nhạy cảm vào tên.
- Không dùng tên người làm owner lâu dài; dùng tên team hoặc service account.
- Không gắn version code vào tên service ổn định nếu nền tảng đã có revision/version riêng.
- Không dùng tên tạm như test2, final-new hoặc latest-prod.
- Kiểm tra quy tắc ký tự, độ dài, phạm vi duy nhất và khả năng đổi tên của từng loại resource.

Một số dịch vụ yêu cầu tên duy nhất toàn cục; một số chỉ duy nhất trong project, account, namespace hoặc region. Có dịch vụ không cho đổi tên sau khi tạo. Khi tên cần duy nhất toàn cục, có thể thêm short organization/project identifier đã được chuẩn hóa.

### 2.2. Không mã hóa quá nhiều thông tin vào tên

Tên resource thường tồn tại lâu hơn cấu trúc team hoặc cách phân bổ chi phí. Nếu tên chứa tên phòng ban, cost center hoặc tên người, mỗi lần tổ chức thay đổi có thể buộc phải tạo lại tài nguyên hoặc duy trì tên sai thực tế.

Nên để tên thể hiện hệ thống và vai trò, còn thông tin dễ thay đổi được quản lý bằng labels/tags. Ví dụ, service có thể giữ tên orders-api trong khi owner thay đổi từ team-commerce sang team-commerce-platform bằng một lần cập nhật metadata.

Region có thể là thành phần của tên nếu cần phân biệt các tài nguyên cùng vai trò ở nhiều region. Nếu region đã được thể hiện rõ trong resource path hoặc project, không cần lặp lại nếu điều đó làm tên quá dài.

## 3. Đặt tên theo loại tài nguyên serverless

Cùng một hệ thống có thể có nhiều thành phần. Hãy chọn danh từ và hậu tố nhất quán để người vận hành phân biệt function, API, worker và event channel.

| Loại tài nguyên | Mẫu tên | Ví dụ |
|---|---|---|
| HTTP service | system-api-env | orders-api-prod |
| Event consumer | system-worker-env | orders-worker-prod |
| Function xử lý một nghiệp vụ | system-action-env | orders-charge-prod |
| Queue | system-purpose-queue-env | orders-payment-queue-prod |
| Topic/event stream | system-events-env | orders-events-prod |
| Workflow | system-process-workflow-env | orders-fulfillment-workflow-prod |
| Batch job | system-purpose-job-env | orders-reconcile-job-prod |
| Storage bucket | org-system-purpose-env-region | acme-orders-archive-prod-asia-southeast1 |
| Service account | system-component-runtime | orders-worker-runtime |
| Secret reference | system-purpose-env | orders-payment-provider-prod |

Các ví dụ chỉ là mẫu logic. Một số nền tảng có loại tài nguyên riêng hoặc quy định naming khác. Ví dụ tên bucket có thể cần duy nhất toàn cầu; tên function có thể bị giới hạn độ dài; queue có thể có suffix do nền tảng thêm vào. Hãy chuẩn hóa tên ở lớp ứng dụng nhưng vẫn tuân theo giới hạn của resource API.

### 3.1. Phân biệt tên service và tên revision

Tên service thường đại diện cho ứng dụng ổn định. Revision hoặc version đại diện cho một lần triển khai cụ thể.

Ví dụ:

~~~text
Service: orders-api-prod
Revision: orders-api-prod-00042
Image: registry.example.com/orders-api@sha256:...
Version: 2.4.1
Commit: 8f31a2c...
~~~

Không cần tạo một service mới cho mỗi lần phát hành nếu nền tảng hỗ trợ revision hoặc alias. Giữ endpoint ổn định và dùng revision/alias để điều phối traffic, canary và rollback.

Với AWS Lambda, có thể giữ tên function ổn định rồi dùng version và alias cho release. Với Cloud Run hoặc Knative, service ổn định có thể có revision mới theo lần deploy. Với Kubernetes, Deployment quản lý ReplicaSet/Pod theo template. Khái niệm và API khác nhau nhưng nguyên tắc giống nhau: tên logical service không nên thay đổi theo mỗi build.

## 4. Môi trường và phạm vi triển khai

Tên môi trường nên dùng một tập giá trị chuẩn, ví dụ:

~~~text
dev
test
staging
prod
~~~

Không trộn các biến thể như production, production1, live, prd và prod nếu chúng cùng biểu diễn một môi trường. Hãy định nghĩa từ điển giá trị chuẩn để pipeline, dashboard và chính sách có thể lọc thống nhất.

Môi trường có thể được phân tách bằng:

- Cloud project hoặc account riêng.
- Kubernetes namespace riêng.
- Region hoặc cluster riêng.
- Resource name có environment suffix.
- Labels/tags environment.
- IAM boundary và secret store riêng.

Không cần dựa vào tên để tạo ranh giới bảo mật. Quyền truy cập phải được thực thi bằng IAM, RBAC, network policy và resource policy. Label environment=prod không ngăn một workload dev truy cập production nếu IAM vẫn cho phép.

### 4.1. Promotion giữa các môi trường

Một quy trình release tốt build artifact một lần rồi promote cùng artifact qua test, staging và production. Mỗi môi trường cung cấp cấu hình và secret riêng.

Ví dụ:

~~~text
Source commit: 8f31a2c
Build ID: build-20261117-042
Artifact digest: sha256:abc123...
Deploy to test: orders-api-test
Deploy to staging: orders-api-staging
Deploy to prod: orders-api-prod
~~~

Nếu build lại artifact riêng cho từng môi trường, khó chứng minh production đang chạy cùng binary đã được kiểm thử. Thay đổi môi trường nên được thể hiện trong cấu hình triển khai, không nên thay đổi bytecode hoặc container image nếu không có lý do rõ ràng.

### 4.2. Môi trường tạm thời

Preview environment cho pull request có thể dùng tên dựa trên số PR hoặc ID ngắn:

~~~text
orders-api-pr-184
orders-worker-pr-184
~~~

Không đưa toàn bộ branch name vào resource name vì branch có thể chứa ký tự không hợp lệ, quá dài hoặc thông tin nội bộ. Dùng nhãn để lưu PR number, commit và thời hạn dọn dẹp.

Tài nguyên tạm cần có owner, expiry/TTL và cơ chế cleanup. Nếu không, preview environment có thể tồn tại sau khi PR đóng và tiếp tục phát sinh chi phí hoặc giữ dữ liệu không cần thiết.

## 5. Labels và tags cho quản trị tài nguyên

Labels/tags nên trả lời các câu hỏi vận hành:

- Tài nguyên thuộc hệ thống nào?
- Team nào chịu trách nhiệm?
- Chi phí cần phân bổ cho cost center nào?
- Tài nguyên thuộc môi trường nào?
- Dữ liệu có mức phân loại nào?
- Tài nguyên được quản lý bằng Terraform, CDK hay công cụ nào?
- Đây là workload production, preview hay batch?

Một bộ key-value cơ bản:

~~~text
system=orders
component=worker
environment=production
team=commerce-platform
cost-center=cc-042
managed-by=terraform
data-classification=internal
~~~

Không phải mọi nền tảng cho phép cùng bộ key hoặc cùng ký tự. Có thể cần chuẩn hóa thành key lowercase và giá trị ngắn để tương thích với các dịch vụ cloud khác nhau.

### 5.1. Bộ label Kubernetes phổ biến

Kubernetes khuyến nghị một số label chuẩn thuộc nhóm app.kubernetes.io. Ví dụ:

~~~yaml
metadata:
  labels:
    app.kubernetes.io/name: orders
    app.kubernetes.io/instance: orders-prod
    app.kubernetes.io/component: worker
    app.kubernetes.io/part-of: commerce-platform
    app.kubernetes.io/managed-by: kustomize
    environment: production
    team: commerce-platform
    cost-center: cc-042
~~~

Ý nghĩa thường gặp:

- app.kubernetes.io/name: tên ứng dụng.
- app.kubernetes.io/instance: một instance triển khai của ứng dụng.
- app.kubernetes.io/component: vai trò như api, worker hoặc scheduler.
- app.kubernetes.io/part-of: hệ thống lớn hơn mà component thuộc về.
- app.kubernetes.io/managed-by: công cụ quản lý tài nguyên.

Những label này giúp công cụ và người vận hành hiểu quan hệ giữa resource. Nếu dùng label trong selector, phải giữ giá trị ổn định và nhất quán giữa Pod template, Service và controller. Không đưa giá trị thay đổi theo mỗi build vào selector.

### 5.2. Tags trên cloud provider

Các cloud provider có cách triển khai tags/labels khác nhau:

- Google Cloud hỗ trợ labels trên nhiều loại tài nguyên để lọc và phân bổ chi phí theo dịch vụ hỗ trợ.
- AWS cung cấp resource tags; một số dịch vụ và tính năng billing cần bật hoặc cấu hình riêng để dùng tag cho cost allocation.
- Azure cung cấp tags trên nhiều tài nguyên; phạm vi kế thừa và hỗ trợ policy phụ thuộc loại resource.

Không giả định mọi tài nguyên đều hỗ trợ tags hoặc mọi tag đều xuất hiện trong báo cáo billing. Kiểm tra tài liệu dịch vụ, giới hạn key/value và cấu hình cost allocation của tài khoản.

Một chính sách gắn nhãn nên được kiểm tra trong CI/IaC hoặc admission policy. Tài nguyên production thiếu owner, environment hoặc cost-center có thể bị cảnh báo hoặc từ chối triển khai theo policy của tổ chức.

## 6. Annotation cho metadata triển khai

Trong Kubernetes, annotation phù hợp với thông tin bổ sung mà controller hoặc người vận hành cần đọc nhưng không cần dùng để chọn Pod.

Ví dụ:

~~~yaml
metadata:
  annotations:
    deployment.example.com/source-revision: "8f31a2c"
    deployment.example.com/build-id: "build-20261117-042"
    deployment.example.com/release-id: "release-2026-11-17.3"
    deployment.example.com/image-digest: "sha256:abc123..."
    deployment.example.com/pipeline: "ci-main"
~~~

Annotation có thể chứa URL tài liệu, commit, build ID hoặc thông tin triển khai. Tránh đưa credential, private key, access token hoặc dữ liệu nhạy cảm vào annotation vì metadata có thể được nhiều người hoặc controller đọc.

Không dùng annotation làm nơi lưu state nghiệp vụ. Annotation là metadata về resource; trạng thái nghiệp vụ cần ở database, queue hoặc workflow state store.

Với cloud resource không có annotation tương đương, dùng tag/label cho metadata ngắn và release manifest hoặc hệ thống deployment để lưu thông tin chi tiết.

## 7. OCI image labels và nhận diện artifact

Container image có thể mang metadata theo chuẩn OCI. Những trường phổ biến gồm title, description, source repository, version, revision, created và license.

Ví dụ Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY target/orders-worker.jar /app/app.jar

LABEL org.opencontainers.image.title="orders-worker"
LABEL org.opencontainers.image.description="Java event consumer for orders"
LABEL org.opencontainers.image.version="2.4.1"
LABEL org.opencontainers.image.revision="8f31a2c"
LABEL org.opencontainers.image.source="https://git.example.com/commerce/orders"
LABEL org.opencontainers.image.created="2026-11-17T10:00:00Z"

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Các label này giúp registry scanner và công cụ vận hành nhận diện image. Chúng không thay thế image digest. Tag như 2.4.1 có thể bị ghi đè nếu registry cho phép; digest nhận diện nội dung image cụ thể.

Triển khai production nên tham chiếu digest khi cần tính bất biến:

~~~text
registry.example.com/commerce/orders-worker@sha256:abc123...
~~~

Dùng digest giúp xác định chính xác binary được triển khai. Nếu dùng tag, cần bảo đảm registry policy không cho ghi đè hoặc pipeline kiểm tra tag đã trỏ đến digest nào.

## 8. Truy nguyên từ source code đến runtime

Traceability cần nối nhiều mắt xích:

~~~mermaid
flowchart LR
    A["Source repository"] --> B["Commit SHA"]
    B --> C["CI build"]
    C --> D["Artifact / image digest"]
    D --> E["Release manifest"]
    E --> F["Deployment"]
    F --> G["Cloud resource / revision"]
    G --> H["Invocation / log / trace"]
~~~

Mỗi mắt xích cần một định danh có thể tra cứu:

| Giai đoạn | Định danh cần lưu |
|---|---|
| Source | Repository, commit SHA, branch hoặc tag release |
| Build | Build ID, pipeline run ID, builder identity, thời điểm |
| Artifact | Package version, OCI image digest, SBOM reference |
| Release | Release ID, môi trường đích, config revision |
| Deployment | Deployment ID, actor/service account, thời điểm, kết quả |
| Runtime | Service/function name, revision/version, region, instance ID |
| Request/event | Request ID, trace ID, event ID, execution ID, correlation ID |

Không phải mọi định danh đều cần làm label. Commit SHA hoặc build ID có cardinality cao; chúng phù hợp với annotation, release record, log hoặc deployment metadata hơn là metric label được gắn cho mọi time series.

### 8.1. Release manifest

Một release manifest có thể ghi lại artifact và cấu hình được triển khai:

~~~json
{
  "service": "orders-worker",
  "environment": "production",
  "releaseId": "release-2026-11-17.3",
  "source": {
    "repository": "commerce/orders",
    "commit": "8f31a2c"
  },
  "build": {
    "id": "build-20261117-042",
    "pipeline": "ci-main"
  },
  "artifact": {
    "image": "registry.example.com/commerce/orders-worker",
    "digest": "sha256:abc123..."
  },
  "configuration": {
    "revision": "config-17",
    "secretReferences": [
      "orders/payment-provider"
    ]
  },
  "deployment": {
    "id": "deploy-20261117-003",
    "region": "asia-southeast1"
  }
}
~~~

Đây là ví dụ cấu trúc. Không ghi secret value vào manifest; chỉ lưu tên hoặc version reference nếu cần truy nguyên. Cũng không ghi credential có thể dùng để truy cập pipeline hoặc cloud account.

Release manifest nên được lưu ở nơi có versioning và quyền truy cập phù hợp. Khi điều tra lỗi, có thể tìm deploy ID từ runtime metadata rồi mở đúng manifest để biết commit, image digest và config revision.

### 8.2. SBOM và build provenance

Software Bill of Materials (SBOM) liệt kê thành phần phần mềm có trong artifact. Build provenance ghi nhận artifact được tạo từ source, builder và quy trình nào.

Hai thông tin này hỗ trợ:

- Điều tra thư viện bị phát hiện lỗ hổng.
- Xác minh artifact được build từ repository và commit được phê duyệt.
- So sánh dependency giữa hai release.
- Chứng minh binary triển khai là artifact đã được CI tạo.
- Hỗ trợ policy kiểm tra chữ ký và nguồn gốc trước khi deploy.

SBOM/provenance nên gắn với digest của artifact. Nếu chỉ gắn với tag có thể thay đổi, mối liên kết với binary cụ thể yếu hơn.

## 9. Cấu hình Java để nhận diện service và deployment

Ứng dụng Java cần phân biệt metadata build với metadata runtime:

- **Build metadata:** version ứng dụng, commit SHA, build ID và thời điểm build.
- **Deployment metadata:** environment, region, release ID và config revision.
- **Instance metadata:** instance/pod ID và thông tin runtime được nền tảng cung cấp.
- **Request metadata:** request ID, trace ID, event ID và correlation ID.

Có thể truyền các giá trị không nhạy cảm bằng environment variables. Không tạo một bộ biến tên khác nhau cho từng môi trường như DB_PASSWORD_PROD, DB_PASSWORD_STAGING. Giữ cùng key cấu hình và cung cấp value hoặc secret reference phù hợp tại môi trường triển khai.

Ví dụ Java 17:

~~~java
public record RuntimeIdentity(
        String serviceName,
        String environment,
        String serviceVersion,
        String commit,
        String buildId,
        String releaseId,
        String region,
        String instanceId) {

    public static RuntimeIdentity fromEnvironment() {
        return new RuntimeIdentity(
                value("APP_NAME", "orders-worker"),
                value("APP_ENV", "unknown"),
                value("APP_VERSION", "unknown"),
                value("GIT_COMMIT", "unknown"),
                value("BUILD_ID", "unknown"),
                value("RELEASE_ID", "unknown"),
                value("CLOUD_REGION", "unknown"),
                value("INSTANCE_ID", "unknown")
        );
    }

    private static String value(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }
}
~~~

Runtime identity giúp log có metadata nhất quán. Các giá trị fallback unknown có ích trong local development, nhưng production có thể kiểm tra bắt buộc APP_NAME, APP_ENV, APP_VERSION và RELEASE_ID khi khởi động để phát hiện cấu hình thiếu.

Không đưa secret vào RuntimeIdentity. Secret cần được đọc từ secret manager hoặc được mount/inject theo cơ chế của nền tảng, chỉ ở nơi cần sử dụng và không serialize vào log.

### 9.1. Spring Boot build information

Spring Boot có thể tạo build information từ Maven/Gradle plugin và cung cấp qua Actuator Info endpoint nếu được cấu hình. Điều này hữu ích để xem version/build metadata của ứng dụng. Tuy nhiên, endpoint info không nên public không kiểm soát; nó có thể tiết lộ commit, dependency hoặc chi tiết triển khai.

Build metadata được đóng gói trong JAR là thông tin tại thời điểm build. Environment, region và release ID là thông tin tại thời điểm deploy. Không trộn hai nhóm vì cùng một image có thể được triển khai sang nhiều môi trường.

## 10. Structured logging và correlation ID

Log cần giúp xác định service, revision và request đã xảy ra ở đâu. Với serverless, một invocation có thể chạy trên instance khác nhau, nên không thể dựa vào tên thread hoặc local file để nối chuỗi sự kiện.

Một log record có cấu trúc có thể chứa:

~~~json
{
  "timestamp": "2026-11-17T13:20:00Z",
  "severity": "INFO",
  "service.name": "orders-worker",
  "service.version": "2.4.1",
  "deployment.environment.name": "production",
  "deployment.id": "deploy-20261117-003",
  "cloud.region": "asia-southeast1",
  "service.instance.id": "instance-7c91",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "correlation_id": "order-1042",
  "event_id": "evt-91f2",
  "message": "Order event processed"
}
~~~

Tên trường cụ thể phụ thuộc logging backend và OpenTelemetry semantic conventions. Dùng cùng một schema trong các service để truy vấn log dễ hơn.

Phân biệt:

- **Request ID:** định danh một HTTP request hoặc invocation ở một lớp.
- **Trace ID:** liên kết các span của một distributed trace.
- **Span ID:** định danh một đoạn xử lý trong trace.
- **Event ID:** định danh một event từ source.
- **Correlation ID:** liên kết nhiều request, event hoặc workflow thuộc cùng nghiệp vụ.
- **Execution ID:** định danh một lần chạy workflow hoặc batch.

Không dùng các ID này thay thế lẫn nhau. Một đơn hàng có thể có nhiều request, nhiều event và nhiều workflow execution nhưng vẫn dùng cùng business correlation ID.

### 10.1. Metadata trong OpenTelemetry

OpenTelemetry Resource mô tả service/process phát telemetry. Các attribute thường dùng gồm:

~~~text
service.name=orders-worker
service.version=2.4.1
deployment.environment.name=production
cloud.region=asia-southeast1
service.instance.id=instance-7c91
~~~

Resource attributes nên được gắn một lần khi khởi tạo telemetry provider. Trace/span attributes bổ sung dữ liệu theo request hoặc thao tác. Không đưa customer ID, order ID hoặc trace ID vào metric labels có cardinality cao; các giá trị này phù hợp hơn với log và trace có kiểm soát.

Nếu nền tảng đã cung cấp trace context qua header hoặc message metadata, hãy tiếp tục context thay vì tạo trace mới không liên kết. Với event, chuyển trace context theo chuẩn được producer/consumer hỗ trợ.

## 11. Truy nguyên event và workflow

Trong xử lý bất đồng bộ, cần giữ định danh xuyên suốt từ producer đến consumer:

~~~text
HTTP request
  request_id = req-123
  correlation_id = order-1042
        |
        v
Order service
  event source = /orders/api
  event id = evt-91f2
        |
        v
Broker / queue
        |
        v
Payment worker
  event_id = evt-91f2
  correlation_id = order-1042
        |
        v
Workflow
  execution_id = exec-7a21
  correlation_id = order-1042
~~~

Khi retry, event ID và idempotency key phải giữ ổn định. Không tạo event ID mới cho mỗi lần gửi lại cùng một sự kiện logic. Nếu phát sinh một event mới do nghiệp vụ thay đổi, tạo ID mới và liên kết bằng correlation ID.

Log nên chứa đủ định danh để tìm toàn bộ chuỗi xử lý, nhưng không cần chứa toàn bộ payload. Với dữ liệu nhạy cảm, log ID tham chiếu đã được kiểm soát thay vì nội dung thực.

## 12. Dùng labels cho cost allocation và ownership

Labels/tags giúp tổng hợp chi phí theo ứng dụng, môi trường, team hoặc cost center nếu dịch vụ billing hỗ trợ. Một quy ước có thể là:

~~~text
system=orders
environment=production
team=commerce-platform
cost-center=cc-042
component=worker
managed-by=terraform
~~~

Để cost allocation đáng tin cậy:

1. Chuẩn hóa key/value và danh mục team, environment, cost center.
2. Gắn metadata vào mọi resource hỗ trợ.
3. Bật tính năng cost allocation/tag activation nếu cloud provider yêu cầu.
4. Kiểm tra tài nguyên không có label hoặc label sai.
5. Phân bổ chi phí shared resource theo quy tắc công khai.
6. Theo dõi chi phí chưa phân loại và xử lý owner.
7. Không dùng label có giá trị thay đổi liên tục.

Một số chi phí không thể gắn trực tiếp vào một service, ví dụ network egress dùng chung, cluster node hoặc shared broker. Có thể phân bổ theo request count, CPU time, message count hoặc một tỷ lệ đã thống nhất. Ghi rõ phương pháp để các nhóm hiểu số liệu.

### 12.1. Cardinality và giới hạn metadata

Không đưa các giá trị thay đổi theo từng request vào labels/tags:

- request_id
- trace_id
- user_id
- order_id
- timestamp
- message_id
- arbitrary exception text

Các giá trị này tạo cardinality cao, làm tăng chi phí lưu trữ metric hoặc vượt giới hạn label của nền tảng. Hãy dùng log/traces để lưu chi tiết theo request; labels/tags chỉ nên chứa một tập giá trị nhỏ, ổn định.

## 13. Quản lý cấu hình và secret theo môi trường

Tên tài nguyên và labels không thay thế cấu hình runtime. Java application có thể dùng cùng một image ở nhiều môi trường với config khác nhau.

Ví dụ biến cấu hình:

~~~text
APP_NAME=orders-worker
APP_ENV=production
APP_VERSION=2.4.1
GIT_COMMIT=8f31a2c
BUILD_ID=build-20261117-042
RELEASE_ID=release-2026-11-17.3
CLOUD_REGION=asia-southeast1
LOG_LEVEL=INFO
PAYMENT_PROVIDER_SECRET_REF=orders/payment-provider
~~~

Các biến trên là metadata/cấu hình không nhạy cảm hoặc secret reference. Không đặt giá trị secret thực trong file .env được commit, image layer, label, annotation hoặc command line có thể bị lưu vào lịch sử.

Cần phân biệt:

- Config không nhạy cảm: environment variables, config file hoặc config service.
- Secret: Secret Manager, cloud secret store hoặc Kubernetes Secret được bảo vệ.
- Resource metadata: labels/tags/annotations.
- Build metadata: version, commit và build ID.
- Runtime telemetry: service/resource attributes và trace context.

Khi cấu hình secret theo version, lưu tên hoặc version reference trong deployment record. Khi secret được rotate, cần biết workload đang dùng version nào mà không ghi nội dung secret.

## 14. Kiểm tra quy ước bằng CI/CD và IaC

Quy ước chỉ hữu ích khi được áp dụng nhất quán. Hãy đưa validation vào pipeline:

- Kiểm tra resource name theo regex và giới hạn của dịch vụ.
- Kiểm tra environment nằm trong danh mục được phép.
- Bắt buộc owner/team, system và cost-center.
- Kiểm tra image được pin theo digest hoặc tag bất biến theo policy.
- Kiểm tra deployment record có commit và build ID.
- Chặn secret trong label, annotation, Dockerfile hoặc log.
- Kiểm tra service account và IAM role có quyền tối thiểu.
- Kiểm tra resource tạm có expiry/owner.
- Kiểm tra selector labels không bị thay đổi ngoài ý muốn.

Ví dụ policy đơn giản trong CI có thể yêu cầu một tập metadata:

~~~yaml
requiredLabels:
  - system
  - environment
  - team
  - cost-center
  - managed-by

allowedEnvironments:
  - dev
  - test
  - staging
  - prod
~~~

Đây là policy minh họa, không phải schema của một công cụ cụ thể. Có thể thực thi bằng script, policy engine, Terraform validation, Kubernetes admission policy hoặc quy tắc của nền tảng.

IaC nên tạo resource và metadata từ cùng một nguồn biến chuẩn. Tránh copy/paste tên giữa nhiều file vì dễ tạo sai khác. Dùng module hoặc template chung cho các service có cấu trúc tương tự, nhưng vẫn giữ tên logical rõ ràng cho từng resource.

## 15. Điều tra sự cố từ runtime về source

Khi một Java function lỗi, quy trình truy nguyên nên đi theo chuỗi:

1. Lấy request ID, trace ID, event ID hoặc workflow execution ID từ alert/log.
2. Tìm service name, environment, region và revision/version.
3. Tìm deployment ID hoặc release ID tương ứng.
4. Mở release manifest để lấy image digest, build ID và commit.
5. Mở pipeline run và artifact provenance.
6. Kiểm tra config revision và secret reference/version, không đọc secret value vào log.
7. So sánh revision hiện tại với revision trước để xác định thay đổi.
8. Kiểm tra dependency, IAM và resource labels để tìm owner chịu trách nhiệm.

Một sự cố có thể do code, config, secret rotation, IAM policy hoặc thay đổi hạ tầng. Nếu chỉ lưu version ứng dụng mà không lưu config revision và deployment ID, rất khó phân biệt code mới với cấu hình mới.

Rollback cũng cần truy nguyên. Quay lại image cũ không tự khôi phục environment variable, secret version hoặc schema database. Release record nên lưu đủ metadata để biết những gì cần rollback cùng artifact.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Mỗi team tự đặt tên | Khó tìm và tự động hóa | Dùng naming convention và từ điển chung |
| Dùng tên resource làm nơi chứa mọi metadata | Tên dài, khó đổi và dễ sai | Đưa owner/environment/cost-center vào labels |
| Gắn commit SHA vào metric label | Cardinality tăng mạnh | Dùng annotation, log hoặc release record |
| Dùng latest cho production | Không biết chính xác binary nào đang chạy | Pin image digest hoặc tag bất biến |
| Không lưu deployment ID | Khó tìm lần triển khai gây lỗi | Ghi release/deployment manifest |
| Dùng label như ranh giới bảo mật | Có thể cấp quyền sai | Dùng IAM/RBAC/resource policy |
| Ghi secret vào annotation hoặc log | Rò rỉ credential | Lưu secret trong secret manager |
| Build lại artifact cho mỗi môi trường | Không chứng minh được artifact đã test | Build một lần, promote cùng digest |
| Không có owner và cost center | Chi phí khó phân bổ | Bắt buộc labels/tags qua CI policy |
| Dùng request ID làm idempotency key cho event | Retry có thể tạo thao tác trùng | Dùng event ID hoặc khóa nghiệp vụ ổn định |

## 17. Checklist triển khai

Trước khi đưa một Java serverless resource vào production, hãy kiểm tra:

1. Tên resource theo convention và tuân thủ giới hạn của dịch vụ.
2. Environment và region được thể hiện nhất quán.
3. Labels/tags có system, component, owner/team và cost center.
4. Annotation chỉ chứa metadata bổ sung, không chứa secret.
5. Kubernetes selector labels ổn định và nhất quán nếu có dùng.
6. Image được nhận diện bằng digest hoặc tag bất biến.
7. OCI metadata có source, version và revision phù hợp.
8. Build ID, commit SHA và artifact provenance được lưu.
9. Deployment ID, release ID và config revision có thể truy vấn.
10. Runtime log có service name/version/environment và correlation ID.
11. Trace context được truyền qua HTTP/event/workflow.
12. Không đưa ID có cardinality cao vào metric labels.
13. Secret được tham chiếu từ secret manager và có quyền tối thiểu.
14. CI/IaC kiểm tra naming, labels và metadata bắt buộc.
15. Có owner và expiry cho tài nguyên tạm.
16. Có cách truy ngược từ alert đến deployment và source commit.

## 18. Câu hỏi tự kiểm tra

- Resource name khác label/tag ở mục đích nào?
- Khi nào nên dùng Kubernetes annotation thay cho label?
- Vì sao tên service ổn định nên tách khỏi revision/version?
- Vì sao environment label không thay thế IAM boundary?
- OCI image digest khác image tag như thế nào?
- Build metadata khác deployment metadata ở đâu?
- Làm thế nào truy từ một log record đến commit đã tạo image?
- Request ID, trace ID, event ID và correlation ID khác nhau thế nào?
- Vì sao không nên đưa trace ID hoặc order ID vào metric label?
- Labels hỗ trợ cost allocation như thế nào và cần cấu hình gì thêm?
- Vì sao build một lần rồi promote cùng artifact qua các môi trường?
- Những thông tin nào cần có trong release manifest để điều tra sự cố?

Đặt tên, gắn nhãn và truy nguyên nguồn triển khai là một phần của thiết kế vận hành serverless. Tên resource cần ổn định và dễ nhận diện; labels/tags giúp phân loại và phân bổ chi phí; annotation và release provenance liên kết runtime với source và artifact. Khi Java service phát log có metadata nhất quán và pipeline lưu image digest cùng deployment record, đội vận hành có thể tìm đúng owner, xác định phiên bản đang chạy và truy ngược thay đổi gây ra sự cố.

